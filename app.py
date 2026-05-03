from flask import Flask, render_template, request, redirect, jsonify
import sqlite3
import json
import os

app = Flask(__name__)
# Filtro necesario para que el HTML entienda los detalles de la venta (formato JSON)
app.jinja_env.filters['fromjson'] = json.loads

def get_db():
    """Conexión a la base de datos local"""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(base_dir, "db.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Crea las tablas y asegura que existan todas las columnas necesarias"""
    db = get_db()
    
    # Tabla de Productos (Stock)
    db.execute("""CREATE TABLE IF NOT EXISTS productos (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        nombre TEXT NOT NULL, 
        precio REAL NOT NULL, 
        stock INTEGER NOT NULL,
        unidad TEXT DEFAULT 'Unidad', 
        oferta TEXT DEFAULT ''
    )""")
    
    # Tabla de Compras (Entradas de mercadería)
    db.execute("""CREATE TABLE IF NOT EXISTS compras (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        lugar TEXT, 
        producto TEXT, 
        cantidad INTEGER, 
        total REAL, 
        fecha TEXT DEFAULT (DATETIME('now','localtime'))
    )""")
    
    # Tabla de Ventas (Salidas y Deudas)
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
    try:
        columnas_ventas = [c['name'] for c in db.execute("PRAGMA table_info(ventas)").fetchall()]
        if 'direccion' not in columnas_ventas:
            db.execute("ALTER TABLE ventas ADD COLUMN direccion TEXT")
        if 'whatsapp' not in columnas_ventas:
            db.execute("ALTER TABLE ventas ADD COLUMN whatsapp TEXT")
    except:
        pass
        
    db.commit()
    db.close()

# Inicializar base de datos al arrancar la app
init_db()

# --- RUTAS DE INVENTARIO (INDEX) ---
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

# --- RUTAS DE VENTAS ---
@app.route("/vender")
def vender():
    return render_template("ventas.html")

@app.route("/productos_json")
def productos_json():
    """Esta ruta alimenta al buscador de productos en Ventas"""
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
    
    # Insertar venta con los nuevos campos (Dirección/WhatsApp)
    db.execute("""INSERT INTO ventas (cliente, direccion, whatsapp, detalle, total, saldo) 
                  VALUES (?,?,?,?,?,?)""",
               (cliente['nombre'], cliente.get('direccion', ''), cliente.get('whatsapp', ''), 
                json.dumps(carrito), total_venta, total_venta))
    
    # Descontar del stock
    for item in carrito:
        db.execute("UPDATE productos SET stock = stock - ? WHERE id = ?", (item['cantidad'], item['id']))
    
    db.commit()
    db.close()
    return jsonify({"ok": True})

# --- RUTAS DE COMPRAS (ENTRADA DE STOCK) ---
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
    try:
        prod_nombre = request.form['producto']
        cant = int(request.form['cantidad'])
        costo_total = float(request.form['total'])
        proveedor = request.form.get('lugar', 'Proveedor General')
        
        # Registrar compra
        db.execute("INSERT INTO compras (lugar, producto, cantidad, total) VALUES (?,?,?,?)",
                   (proveedor, prod_nombre, cant, costo_total))
        
        # Actualizar stock del producto
        db.execute("UPDATE productos SET stock = stock + ? WHERE nombre = ?", (cant, prod_nombre))
        db.commit()
    except Exception as e:
        print(f"Error en compra: {e}")
    finally:
        db.close()
    return redirect("/compras")

# --- RUTAS DE COBRANZAS (BOLETAS) ---
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

# --- DASHBOARD (RESUMEN) ---
@app.route("/dashboard")
def dashboard():
    db = get_db()
    v = db.execute("SELECT SUM(total) FROM ventas").fetchone()[0] or 0
    c = db.execute("SELECT SUM(total) FROM compras").fetchone()[0] or 0
    alerta = db.execute("SELECT COUNT(id) FROM productos WHERE stock < 10").fetchone()[0] or 0
    db.close()
    return render_template("dashboard.html", total_ventas=v, total_compras=c, ganancia=v-c, alertas_stock=alerta)

if __name__ == "__main__":
    # Importante: host 0.0.0.0 permite que otros dispositivos en tu WiFi vean la app
    app.run(host="0.0.0.0", port=10000, debug=True)
