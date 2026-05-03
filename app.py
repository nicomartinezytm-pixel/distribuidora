from flask import Flask, render_template, request, redirect, jsonify
import sqlite3
import json
import os

app = Flask(__name__)
app.jinja_env.filters['fromjson'] = json.loads

def get_db():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    conn = sqlite3.connect(os.path.join(base_dir, "db.db"))
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    db = get_db()
    # PRODUCTOS: Inventario central
    db.execute("""
        CREATE TABLE IF NOT EXISTS productos (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            nombre TEXT, precio REAL, stock INTEGER, unidad TEXT, oferta TEXT
        )""")
    # COMPRAS: Lo que nosotros compramos a mayoristas (Abastecimiento)
    db.execute("""
        CREATE TABLE IF NOT EXISTS compras (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            lugar TEXT, direccion TEXT, producto TEXT, 
            cantidad INTEGER, total REAL, fecha TEXT DEFAULT (DATETIME('now','localtime'))
        )""")
    # VENTAS: Lo que vendemos a nuestros clientes
    db.execute("""
        CREATE TABLE IF NOT EXISTS ventas (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            cliente TEXT, direccion TEXT, telefono TEXT, detalle TEXT, 
            total REAL, pagado REAL DEFAULT 0, saldo REAL DEFAULT 0, 
            estado TEXT DEFAULT 'fiado', fecha TEXT DEFAULT (DATETIME('now','localtime'))
        )""")
    db.commit()
    db.close()

init_db()

@app.route("/")
def index():
    db = get_db()
    productos = db.execute("SELECT * FROM productos ORDER BY nombre ASC").fetchall()
    db.close()
    return render_template("index.html", productos=productos)

@app.route("/productos_json")
def productos_json():
    db = get_db()
    productos = db.execute("SELECT id, nombre, precio, stock, unidad, oferta FROM productos").fetchall()
    db.close()
    return jsonify([dict(p) for p in productos])

# --- PANEL DE CONTROL: COMPRAS (ABASTECIMIENTO) ---
@app.route("/compras")
def compras():
    db = get_db()
    historial = db.execute("SELECT * FROM compras ORDER BY id DESC").fetchall()
    productos = db.execute("SELECT nombre, stock FROM productos ORDER BY nombre ASC").fetchall()
    db.close()
    return render_template("compras.html", historial=historial, productos=productos)

@app.route("/agregar_compra", methods=["POST"])
def agregar_compra():
    db = get_db()
    lugar = request.form["lugar"]
    direccion = request.form["direccion"]
    producto = request.form["producto"]
    cantidad = int(request.form["cantidad"])
    total = float(request.form["total"])
    db.execute("INSERT INTO compras (lugar, direccion, producto, cantidad, total) VALUES (?, ?, ?, ?, ?)",
               (lugar, direccion, producto, cantidad, total))
    # SUMAR AL STOCK
    db.execute("UPDATE productos SET stock = stock + ? WHERE nombre = ?", (cantidad, producto))
    db.commit()
    db.close()
    return redirect("/compras")

@app.route("/eliminar_compra/<int:id>")
def eliminar_compra(id):
    db = get_db()
    compra = db.execute("SELECT producto, cantidad FROM compras WHERE id=?", (id,)).fetchone()
    if compra:
        db.execute("UPDATE productos SET stock = stock - ? WHERE nombre = ?", (compra["cantidad"], compra["producto"]))
    db.execute("DELETE FROM compras WHERE id=?", (id,))
    db.commit()
    db.close()
    return redirect("/compras")

# --- SISTEMA DE VENTAS ---
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
            sub = p["precio"] * item["cantidad"]
            total_venta += sub
            detalle_lista.append({"nombre": p["nombre"], "cantidad": item["cantidad"], "precio": p["precio"], "subtotal": sub})
            # RESTAR DEL STOCK
            db.execute("UPDATE productos SET stock = stock - ? WHERE id=?", (item["cantidad"], item["id"]))
    
    db.execute("INSERT INTO ventas (cliente, direccion, telefono, detalle, total, pagado, saldo, estado) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
               (data["cliente"]["nombre"], data["cliente"]["direccion"], data["cliente"]["telefono"], json.dumps(detalle_lista), total_venta, 0, total_venta, "fiado"))
    db.commit()
    db.close()
    return jsonify({"ok": True})

# --- GESTION DE CLIENTES Y BOLETAS ---
@app.route("/boletas")
def boletas():
    db = get_db()
    res = db.execute("SELECT * FROM ventas ORDER BY id DESC").fetchall()
    db.close()
    return render_template("boletas.html", boletas=res)

@app.route("/clientes")
def clientes():
    db = get_db()
    query = """SELECT cliente, direccion, telefono, SUM(total) as total_gastado, 
               SUM(saldo) as deuda_total, COUNT(id) as total_compras 
               FROM ventas GROUP BY cliente ORDER BY deuda_total DESC"""
    res = db.execute(query).fetchall()
    db.close()
    return render_template("clientes.html", clientes=res)

@app.route("/dashboard")
def dashboard():
    db = get_db()
    v = db.execute("SELECT SUM(total) FROM ventas").fetchone()[0] or 0
    c = db.execute("SELECT SUM(total) FROM compras").fetchone()[0] or 0
    db.close()
    return render_template("dashboard.html", total_ventas=v, total_compras=c, ganancia=v-c)

# --- RUTAS DE CONFIGURACIÓN ---
@app.route("/agregar_producto", methods=["POST"])
def agregar_producto():
    db = get_db()
    db.execute("INSERT INTO productos (nombre, precio, stock, unidad, oferta) VALUES (?, ?, ?, ?, ?)", 
               (request.form["nombre"], float(request.form["precio"]), int(request.form["stock"]), request.form.get("unidad", "Unidad"), request.form.get("oferta", "")))
    db.commit()
    db.close()
    return redirect("/")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
