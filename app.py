from flask import Flask, render_template, request, redirect, jsonify
import sqlite3
import json
import os

app = Flask(__name__)

# Filtro para que el HTML pueda leer el detalle JSON de las ventas
app.jinja_env.filters['fromjson'] = json.loads

def get_db():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    conn = sqlite3.connect(os.path.join(base_dir, "db.db"))
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    db = get_db()
    # Tabla de productos
    db.execute("""
        CREATE TABLE IF NOT EXISTS productos (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            nombre TEXT, 
            precio REAL, 
            stock INTEGER
        )""")
    # Tabla de compras (Entrada de mercadería)
    db.execute("""
        CREATE TABLE IF NOT EXISTS compras (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            lugar TEXT, 
            producto TEXT, 
            cantidad INTEGER, 
            total REAL, 
            fecha TEXT DEFAULT (DATETIME('now','localtime'))
        )""")
    # Tabla de ventas (Boletas y Deudas)
    db.execute("""
        CREATE TABLE IF NOT EXISTS ventas (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            cliente TEXT, 
            direccion TEXT, 
            detalle TEXT, 
            total REAL, 
            pagado REAL DEFAULT 0, 
            saldo REAL DEFAULT 0, 
            estado TEXT DEFAULT 'fiado', 
            fecha TEXT DEFAULT (DATETIME('now','localtime'))
        )""")
    db.commit()
    db.close()

# Inicializar la base de datos al arrancar
init_db()

# --- RUTAS DE INVENTARIO ---

@app.route("/")
def index():
    db = get_db()
    productos = db.execute("SELECT * FROM productos").fetchall()
    db.close()
    return render_template("index.html", productos=productos)

@app.route("/productos_json")
def productos_json():
    db = get_db()
    productos = db.execute("SELECT id, nombre, precio, stock FROM productos").fetchall()
    db.close()
    return jsonify([dict(p) for p in productos])

@app.route("/agregar_producto", methods=["POST"])
def agregar_producto():
    db = get_db()
    nombre = request.form["nombre"]
    precio = float(request.form["precio"])
    stock = int(request.form["stock"])
    db.execute("INSERT INTO productos (nombre, precio, stock) VALUES (?, ?, ?)", (nombre, precio, stock))
    db.commit()
    db.close()
    return redirect("/")

@app.route("/eliminar_producto/<int:id>")
def eliminar_producto(id):
    db = get_db()
    db.execute("DELETE FROM productos WHERE id=?", (id,))
    db.commit()
    db.close()
    return redirect("/")

# --- RUTAS DE COMPRAS (ENTRADA) ---

@app.route("/agregar_compra", methods=["POST"])
def agregar_compra():
    db = get_db()
    lugar = request.form["lugar"]
    prod_nom = request.form["producto"]
    cant = int(request.form["cantidad"])
    total = float(request.form["total"])
    
    db.execute("INSERT INTO compras (lugar, producto, cantidad, total) VALUES (?, ?, ?, ?)", 
               (lugar, prod_nom, cant, total))
    
    # Actualiza stock si el nombre coincide exactamente con un producto existente
    db.execute("UPDATE productos SET stock = stock + ? WHERE nombre = ?", (cant, prod_nom))
    
    db.commit()
    db.close()
    return redirect("/")

# --- RUTAS DE VENTAS (SALIDA) ---

@app.route("/vender")
def vender():
    return render_template("ventas.html")

@app.route("/finalizar_venta", methods=["POST"])
def finalizar_venta():
    db = get_db()
    data = json.loads(request.form["data"])
    total_venta = 0
    detalle_lista = []
    
    for item in data["carrito"]:
        p = db.execute("SELECT * FROM productos WHERE id=?", (item["id"],)).fetchone()
        if p:
            subtotal = p["precio"] * item["cantidad"]
            total_venta += subtotal
            detalle_lista.append({
                "nombre": p["nombre"], 
                "cantidad": item["cantidad"], 
                "precio": p["precio"], 
                "subtotal": subtotal
            })
            # Restar stock
            db.execute("UPDATE productos SET stock = stock - ? WHERE id=?", (item["cantidad"], item["id"]))
    
    pagado_inicial = float(data.get("pagado") or 0)
    saldo_pendiente = max(0, total_venta - pagado_inicial)
    
    # Definir estado inicial
    if saldo_pendiente <= 0:
        estado = "pagado"
    elif pagado_inicial > 0:
        estado = "parcial"
    else:
        estado = "fiado"
    
    db.execute("""
        INSERT INTO ventas (cliente, direccion, detalle, total, pagado, saldo, estado) 
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (data["cliente"]["nombre"], data["cliente"]["direccion"], json.dumps(detalle_lista), 
          total_venta, pagado_inicial, saldo_pendiente, estado))
    
    db.commit()
    db.close()
    return jsonify({"ok": True})

# --- GESTIÓN DE BOLETAS Y COBROS ---

@app.route("/boletas")
def boletas():
    db = get_db()
    res = db.execute("SELECT * FROM ventas ORDER BY id DESC").fetchall()
    db.close()
    return render_template("boletas.html", boletas=res)

@app.route("/pagar_boleta/<int:id>", methods=["POST"])
def pagar_boleta(id):
    db = get_db()
    monto_nuevo_pago = float(request.form.get("monto", 0))
    
    venta = db.execute("SELECT total, pagado FROM ventas WHERE id=?", (id,)).fetchone()
    
    if venta:
        nuevo_total_pagado = venta["pagado"] + monto_nuevo_pago
        nuevo_saldo = max(0, venta["total"] - nuevo_total_pagado)
        
        if nuevo_saldo <= 0:
            nuevo_estado = "pagado"
        else:
            nuevo_estado = "parcial"
            
        db.execute("""
            UPDATE ventas 
            SET pagado = ?, saldo = ?, estado = ? 
            WHERE id = ?
        """, (nuevo_total_pagado, nuevo_saldo, nuevo_estado, id))
        db.commit()
    
    db.close()
    return redirect("/boletas")

@app.route("/eliminar_venta/<int:id>")
def eliminar_venta(id):
    db = get_db()
    venta = db.execute("SELECT detalle FROM ventas WHERE id=?", (id,)).fetchone()
    
    if venta:
        detalle = json.loads(venta["detalle"])
        for item in detalle:
            # Devolvemos el stock al anular la boleta
            db.execute("UPDATE productos SET stock = stock + ? WHERE nombre = ?", 
                       (item["cantidad"], item["nombre"]))
    
    db.execute("DELETE FROM ventas WHERE id=?", (id,))
    db.commit()
    db.close()
    return redirect("/boletas")

# --- CLIENTES Y DASHBOARD ---

@app.route("/clientes")
def clientes():
    db = get_db()
    # Agrupa por cliente y suma sus estadísticas
    res = db.execute("""
        SELECT cliente, 
               SUM(total) as total, 
               COUNT(id) as visitas
        FROM ventas 
        GROUP BY cliente 
        ORDER BY total DESC
    """).fetchall()
    db.close()
    return render_template("clientes.html", clientes=res)

@app.route("/dashboard")
def dashboard():
    db = get_db()
    ventas_totales = db.execute("SELECT SUM(total) FROM ventas").fetchone()[0] or 0
    compras_totales = db.execute("SELECT SUM(total) FROM compras").fetchone()[0] or 0
    db.close()
    return render_template("dashboard.html", 
                           total_ventas=ventas_totales, 
                           total_compras=compras_totales, 
                           ganancia=ventas_totales - compras_totales)

if __name__ == "__main__":
    # Cambia el puerto si es necesario para tu hosting (10000 es común en Render)
    app.run(host="0.0.0.0", port=10000)
