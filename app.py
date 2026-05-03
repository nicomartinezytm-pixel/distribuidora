from flask import Flask, render_template, request, redirect, jsonify
import sqlite3
import json
import os

app = Flask(__name__)
app.jinja_env.filters['fromjson'] = json.loads

def get_db():
    """Conexión a la base de datos local"""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    conn = sqlite3.connect(os.path.join(base_dir, "db.db"))
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Crea las tablas y agrega columnas nuevas si faltan"""
    db = get_db()
    
    # Tabla de Productos
    db.execute("""CREATE TABLE IF NOT EXISTS productos (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        nombre TEXT NOT NULL, 
        precio REAL NOT NULL, 
        stock INTEGER NOT NULL,
        unidad TEXT DEFAULT 'Unidad', 
        oferta TEXT DEFAULT ''
    )""")
    
    # Tabla de Compras
    db.execute("""CREATE TABLE IF NOT EXISTS compras (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        lugar TEXT, 
        producto TEXT, 
        cantidad INTEGER, 
        total REAL, 
        fecha TEXT DEFAULT (DATETIME('now','localtime'))
    )""")
    
    # Tabla de Ventas (Actualizada con Dirección y WhatsApp)
    db.execute("""CREATE TABLE IF NOT EXISTS ventas (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        cliente TEXT, 
        direccion TEXT,
        whatsapp TEXT,
        detalle TEXT, 
        total REAL, 
        pagado REAL DEFAULT 0, 
        saldo REAL DEFAULT 0, 
        estado TEXT DEFAULT 'fiado', 
        fecha TEXT DEFAULT (DATETIME('now','localtime'))
    )""")

    # --- PARCHE DE SEGURIDAD: Agregar columnas si la DB ya existía ---
    columnas_ventas = [c['name'] for c in db.execute("PRAGMA table_info(ventas)").fetchall()]
    if 'direccion' not in columnas_ventas:
        db.execute("ALTER TABLE ventas ADD COLUMN direccion TEXT")
    if 'whatsapp' not in columnas_ventas:
        db.execute("ALTER TABLE ventas ADD COLUMN whatsapp TEXT")
        
    db.commit()
    db.close()

init_db()

# --- RUTAS DE STOCK ---
@app.route("/")
def index():
    db = get_db()
    rows = db.execute("SELECT * FROM productos ORDER BY nombre ASC").fetchall()
    db.close()
    return render_template("index.html", productos=rows)

@app.route("/agregar_producto", methods=["POST"])
def agregar_producto():
    db = get_db()
    db.execute("INSERT INTO productos (nombre, precio, stock, unidad, oferta) VALUES (?, ?, ?, ?, ?)",
               (request.form['nombre'], float(request.form['precio']), 
                int(request.form['stock']), request.form['unidad'], request.form['oferta']))
    db.commit()
    db.close()
    return redirect("/")

# --- RUTA DASHBOARD ---
@app.route("/dashboard")
def dashboard():
    db = get_db()
    v = db.execute("SELECT SUM(total) FROM ventas").fetchone()[0] or 0
    c = db.execute("SELECT SUM(total) FROM compras").fetchone()[0] or 0
    alerta = db.execute("SELECT COUNT(id) FROM productos WHERE stock < 10").fetchone()[0] or 0
    db.close()
    return render_template("dashboard.html", total_ventas=v, total_compras=c, ganancia=v-c, alertas_stock=alerta)

# --- RUTAS DE COMPRAS ---
@app.route("/compras")
def compras():
    db = get_db()
    historial = db.execute("SELECT * FROM compras ORDER BY id DESC LIMIT 20").fetchall()
    prods = db.execute("SELECT nombre FROM productos ORDER BY nombre ASC").fetchall()
    db.close()
    return render_template("compras.html", historial=historial, productos=prods)

@app.route("/agregar_compra", methods=["POST"])
def agregar_compra():
    db = get_db()
    prod_nombre = request.form['producto']
    cant = int(request.form['cantidad'])
    db.execute("INSERT INTO compras (lugar, producto, cantidad, total) VALUES (?,?,?,?)",
               (request.form['lugar'], prod_nombre, cant, float(request.form['total'])))
    db.execute("UPDATE productos SET stock = stock + ? WHERE nombre = ?", (cant, prod_nombre))
    db.commit()
    db.close()
    return redirect("/compras")

# --- RUTAS DE VENTAS ---
@app.route("/vender")
def vender():
    return render_template("ventas.html")

@app.route("/productos_json")
def productos_json():
    db = get_db()
    res = db.execute("SELECT * FROM productos WHERE stock > 0").fetchall()
    db.close()
    return jsonify([dict(r) for r in res])

@app.route("/finalizar_venta", methods=["POST"])
def finalizar_venta():
    db = get_db()
    data = request.json
    cliente = data["cliente"]
    carrito = data["carrito"]
    
    total_venta = sum(float(i['precio']) * int(i['cantidad']) for i in carrito)
    
    # Insertar con los nuevos campos
    db.execute("""INSERT INTO ventas (cliente, direccion, whatsapp, detalle, total, saldo) 
                  VALUES (?,?,?,?,?,?)""",
               (cliente['nombre'], cliente.get('direccion', ''), cliente.get('whatsapp', ''), 
                json.dumps(carrito), total_venta, total_venta))
    
    for item in carrito:
        db.execute("UPDATE productos SET stock = stock - ? WHERE id = ?", (item['cantidad'], item['id']))
    
    db.commit()
    db.close()
    return jsonify({"ok": True})

# --- RUTAS DE COBRANZAS ---
@app.route("/boletas")
def boletas():
    db = get_db()
    res = db.execute("SELECT * FROM ventas ORDER BY id DESC").fetchall()
    db.close()
    return render_template("boletas.html", boletas=res)

@app.route("/registrar_pago", methods=["POST"])
def registrar_pago():
    db = get_db()
    id_v = request.form['id']
    monto = float(request.form['monto'])
    
    v = db.execute("SELECT total, pagado FROM ventas WHERE id=?", (id_v,)).fetchone()
    nuevo_pagado = v['pagado'] + monto
    nuevo_saldo = max(0, v['total'] - nuevo_pagado)
    estado = "pagado" if nuevo_saldo <= 0 else "parcial"
    
    db.execute("UPDATE ventas SET pagado=?, saldo=?, estado=? WHERE id=?", 
               (nuevo_pagado, nuevo_saldo, estado, id_v))
    db.commit()
    db.close()
    return redirect("/boletas")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000, debug=False)
