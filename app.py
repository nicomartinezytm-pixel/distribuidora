from flask import Flask, render_template, request, redirect, jsonify
import sqlite3
import json
import os

app = Flask(__name__)

# Permite leer el detalle JSON de las boletas directamente en el HTML
app.jinja_env.filters['fromjson'] = json.loads

def get_db():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    conn = sqlite3.connect(os.path.join(base_dir, "db.db"))
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    db = get_db()
    db.execute("CREATE TABLE IF NOT EXISTS productos (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT, precio REAL, stock INTEGER)")
    db.execute("CREATE TABLE IF NOT EXISTS compras (id INTEGER PRIMARY KEY AUTOINCREMENT, lugar TEXT, producto TEXT, cantidad INTEGER, total REAL, fecha TEXT DEFAULT (DATETIME('now','localtime')))")
    db.execute("CREATE TABLE IF NOT EXISTS ventas (id INTEGER PRIMARY KEY AUTOINCREMENT, cliente TEXT, direccion TEXT, detalle TEXT, total REAL, pagado REAL DEFAULT 0, saldo REAL DEFAULT 0, estado TEXT DEFAULT 'fiado', fecha TEXT DEFAULT (DATETIME('now','localtime')))")
    db.commit()
    db.close()

init_db()

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

@app.route("/agregar_compra", methods=["POST"])
def agregar_compra():
    db = get_db()
    lugar = request.form["lugar"]
    prod_nom = request.form["producto"]
    cant = int(request.form["cantidad"])
    total = float(request.form["total"])
    db.execute("INSERT INTO compras (lugar, producto, cantidad, total) VALUES (?, ?, ?, ?)", (lugar, prod_nom, cant, total))
    # 🔥 Actualiza stock si el nombre coincide exactamente
    db.execute("UPDATE productos SET stock = stock + ? WHERE nombre = ?", (cant, prod_nom))
    db.commit()
    db.close()
    return redirect("/")

@app.route("/vender")
def vender():
    return render_template("ventas.html")

@app.route("/finalizar_venta", methods=["POST"])
def finalizar_venta():
    db = get_db()
    data = json.loads(request.form["data"])
    total = 0
    detalle = []
    for item in data["carrito"]:
        p = db.execute("SELECT * FROM productos WHERE id=?", (item["id"],)).fetchone()
        if p:
            sub = p["precio"] * item["cantidad"]
            total += sub
            detalle.append({"nombre": p["nombre"], "cantidad": item["cantidad"], "precio": p["precio"], "subtotal": sub})
            db.execute("UPDATE productos SET stock = stock - ? WHERE id=?", (item["cantidad"], item["id"]))
    
    pagado = float(data.get("pagado") or 0)
    saldo = max(0, total - pagado)
    estado = "pagado" if saldo <= 0 else ("parcial" if pagado > 0 else "fiado")
    
    db.execute("INSERT INTO ventas (cliente, direccion, detalle, total, pagado, saldo, estado) VALUES (?, ?, ?, ?, ?, ?, ?)",
               (data["cliente"]["nombre"], data["cliente"]["direccion"], json.dumps(detalle), total, pagado, saldo, estado))
    db.commit()
    db.close()
    return jsonify({"ok": True})

@app.route("/clientes")
def clientes():
    db = get_db()
    res = db.execute("SELECT cliente, SUM(total) as total FROM ventas GROUP BY cliente ORDER BY total DESC").fetchall()
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
