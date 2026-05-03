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
    # Tablas con persistencia
    db.execute("""CREATE TABLE IF NOT EXISTS productos (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        nombre TEXT NOT NULL, precio REAL NOT NULL, stock INTEGER NOT NULL,
        unidad TEXT DEFAULT 'Unidad', oferta TEXT DEFAULT ''
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS compras (
        id INTEGER PRIMARY KEY AUTOINCREMENT, lugar TEXT, producto TEXT, 
        cantidad INTEGER, total REAL, fecha TEXT DEFAULT (DATETIME('now','localtime'))
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS ventas (
        id INTEGER PRIMARY KEY AUTOINCREMENT, cliente TEXT, direccion TEXT, 
        detalle TEXT, total REAL, pagado REAL DEFAULT 0, saldo REAL DEFAULT 0, 
        estado TEXT DEFAULT 'fiado', fecha TEXT DEFAULT (DATETIME('now','localtime'))
    )""")
    db.commit()
    db.close()

init_db()

@app.route("/dashboard")
def dashboard():
    db = get_db()
    v = db.execute("SELECT SUM(total) FROM ventas").fetchone()[0] or 0
    c = db.execute("SELECT SUM(total) FROM compras").fetchone()[0] or 0
    alerta = db.execute("SELECT COUNT(id) FROM productos WHERE stock < 10").fetchone()[0] or 0
    db.close()
    return render_template("dashboard.html", total_ventas=v, total_compras=c, ganancia=v-c, alertas_stock=alerta)

@app.route("/")
def index():
    db = get_db()
    rows = db.execute("SELECT * FROM productos ORDER BY nombre ASC").fetchall()
    db.close()
    return render_template("index.html", productos=rows)

@app.route("/productos_json")
def productos_json():
    db = get_db()
    res = db.execute("SELECT * FROM productos").fetchall()
    db.close()
    return jsonify([dict(r) for r in res])

@app.route("/agregar_producto", methods=["POST"])
def agregar():
    db = get_db()
    db.execute("INSERT INTO productos (nombre, precio, stock, unidad, oferta) VALUES (?,?,?,?,?)",
               (request.form['nombre'], request.form['precio'], request.form['stock'], request.form['unidad'], request.form['oferta']))
    db.commit()
    return redirect("/")

@app.route("/finalizar_venta", methods=["POST"])
def finalizar_venta():
    db = get_db()
    data = json.loads(request.form["data"])
    total = 0
    for item in data["carrito"]:
        sub = float(item["precio"]) * int(item["cantidad"])
        total += sub
        db.execute("UPDATE productos SET stock = stock - ? WHERE id = ?", (item["cantidad"], item["id"]))
    db.execute("INSERT INTO ventas (cliente, detalle, total, saldo) VALUES (?,?,?,?)",
               (data["cliente"]["nombre"], json.dumps(data["carrito"]), total, total))
    db.commit()
    return jsonify({"ok": True})

@app.route("/boletas")
def boletas():
    db = get_db()
    res = db.execute("SELECT * FROM ventas ORDER BY id DESC").fetchall()
    return render_template("boletas.html", boletas=res)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000, debug=True)
