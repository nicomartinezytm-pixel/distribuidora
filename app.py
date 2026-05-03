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

# Esta función crea todo de cero con las columnas correctas
def init_db():
    db = get_db()
    # TABLA PRODUCTOS (Con unidad y oferta desde el inicio)
    db.execute("""
        CREATE TABLE IF NOT EXISTS productos (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            nombre TEXT NOT NULL, 
            precio REAL NOT NULL, 
            stock INTEGER NOT NULL, 
            unidad TEXT DEFAULT 'Unidad', 
            oferta TEXT DEFAULT ''
        )""")
    
    # TABLA COMPRAS (Abastecimiento de la distribuidora)
    db.execute("""
        CREATE TABLE IF NOT EXISTS compras (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            lugar TEXT, 
            direccion TEXT, 
            producto TEXT, 
            cantidad INTEGER, 
            total REAL, 
            fecha TEXT DEFAULT (DATETIME('now','localtime'))
        )""")
    
    # TABLA VENTAS
    db.execute("""
        CREATE TABLE IF NOT EXISTS ventas (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            cliente TEXT, 
            direccion TEXT, 
            telefono TEXT, 
            detalle TEXT, 
            total REAL, 
            pagado REAL DEFAULT 0, 
            saldo REAL DEFAULT 0, 
            estado TEXT DEFAULT 'fiado', 
            fecha TEXT DEFAULT (DATETIME('now','localtime'))
        )""")
    db.commit()
    db.close()

# Ejecutamos la creación de tablas
init_db()

@app.route("/")
def index():
    db = get_db()
    productos = db.execute("SELECT * FROM productos ORDER BY nombre ASC").fetchall()
    db.close()
    return render_template("index.html", productos=productos)

@app.route("/agregar_producto", methods=["POST"])
def agregar_producto():
    try:
        db = get_db()
        nombre = request.form.get("nombre")
        precio = float(request.form.get("precio", 0))
        stock = int(request.form.get("stock", 0))
        unidad = request.form.get("unidad", "Unidad")
        oferta = request.form.get("oferta", "")
        
        db.execute("INSERT INTO productos (nombre, precio, stock, unidad, oferta) VALUES (?, ?, ?, ?, ?)", 
                   (nombre, precio, stock, unidad, oferta))
        db.commit()
        db.close()
        return redirect("/")
    except Exception as e:
        # Esto te dirá exactamente qué falla si vuelve a pasar
        return f"Error detallado: {e}", 500

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
    lugar = request.form.get("lugar")
    direccion = request.form.get("direccion")
    producto = request.form.get("producto")
    cantidad = int(request.form.get("cantidad", 0))
    total = float(request.form.get("total", 0))
    
    db.execute("INSERT INTO compras (lugar, direccion, producto, cantidad, total) VALUES (?, ?, ?, ?, ?)",
               (lugar, direccion, producto, cantidad, total))
    db.execute("UPDATE productos SET stock = stock + ? WHERE nombre = ?", (cantidad, producto))
    db.commit()
    db.close()
    return redirect("/compras")

@app.route("/vender")
def vender():
    return render_template("ventas.html")

@app.route("/productos_json")
def productos_json():
    db = get_db()
    productos = db.execute("SELECT id, nombre, precio, stock, unidad, oferta FROM productos").fetchall()
    db.close()
    return jsonify([dict(p) for p in productos])

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
            db.execute("UPDATE productos SET stock = stock - ? WHERE id=?", (item["cantidad"], item["id"]))
    
    db.execute("INSERT INTO ventas (cliente, direccion, telefono, detalle, total, pagado, saldo, estado) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
               (data["cliente"]["nombre"], data["cliente"]["direccion"], data["cliente"]["telefono"], json.dumps(detalle_lista), total_venta, 0, total_venta, "fiado"))
    db.commit()
    db.close()
    return jsonify({"ok": True})

@app.route("/clientes")
def clientes():
    db = get_db()
    res = db.execute("SELECT cliente, direccion, telefono, SUM(total) as total_gastado, SUM(saldo) as deuda_total, COUNT(id) as total_compras FROM ventas GROUP BY cliente ORDER BY deuda_total DESC").fetchall()
    db.close()
    return render_template("clientes.html", clientes=res)

@app.route("/boletas")
def boletas():
    db = get_db()
    res = db.execute("SELECT * FROM ventas ORDER BY id DESC").fetchall()
    db.close()
    return render_template("boletas.html", boletas=res)

@app.route("/dashboard")
def dashboard():
    db = get_db()
    v = db.execute("SELECT SUM(total) FROM ventas").fetchone()[0] or 0
    c = db.execute("SELECT SUM(total) FROM compras").fetchone()[0] or 0
    db.close()
    return render_template("dashboard.html", total_ventas=v, total_compras=c, ganancia=v-c)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
