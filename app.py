from flask import Flask, render_template, request, redirect, jsonify
import sqlite3
import json
import os

app = Flask(__name__)

# ---------------- DB ----------------
def get_db():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    conn = sqlite3.connect(os.path.join(base_dir, "db.db"))
    conn.row_factory = sqlite3.Row
    return conn


# ---------------- INIT DB ----------------
def init_db():
    db = get_db()

    db.execute("""
    CREATE TABLE IF NOT EXISTS productos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT,
        precio REAL,
        stock INTEGER
    )
    """)

    db.execute("""
    CREATE TABLE IF NOT EXISTS clientes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT,
        telefono TEXT,
        direccion TEXT
    )
    """)

    db.execute("""
    CREATE TABLE IF NOT EXISTS ventas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cliente_id INTEGER,
        total REAL,
        fecha TEXT DEFAULT (DATETIME('now','localtime'))
    )
    """)

    db.execute("""
    CREATE TABLE IF NOT EXISTS compras (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        producto TEXT,
        lugar TEXT,
        cantidad INTEGER,
        total REAL,
        precio_unitario REAL,
        fecha TEXT DEFAULT (DATETIME('now','localtime'))
    )
    """)

    db.commit()
    db.close()


init_db()


# ---------------- HOME ----------------
@app.route("/")
def index():
    db = get_db()
    productos = db.execute("SELECT * FROM productos").fetchall()
    db.close()
    return render_template("index.html", productos=productos)


# ---------------- PRODUCTOS ----------------
@app.route("/agregar_producto", methods=["POST"])
def agregar_producto():
    db = get_db()

    nombre = request.form["nombre"]
    precio = float(request.form["precio"])
    stock = int(request.form["stock"])

    db.execute("""
        INSERT INTO productos (nombre, precio, stock)
        VALUES (?, ?, ?)
    """, (nombre, precio, stock))

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


# ---------------- COMPRAS MAYORISTAS ----------------
@app.route("/agregar_compra", methods=["POST"])
def agregar_compra():
    db = get_db()

    producto = request.form["producto"]
    lugar = request.form["lugar"]
    cantidad = int(request.form["cantidad"])
    total = float(request.form["total"])

    precio_unitario = total / cantidad if cantidad > 0 else 0

    # sumar stock automático
    prod = db.execute("SELECT * FROM productos WHERE nombre=?", (producto,)).fetchone()

    if prod:
        db.execute("""
            UPDATE productos
            SET stock = stock + ?
            WHERE nombre=?
        """, (cantidad, producto))

    db.execute("""
        INSERT INTO compras (producto, lugar, cantidad, total, precio_unitario)
        VALUES (?, ?, ?, ?, ?)
    """, (producto, lugar, cantidad, total, precio_unitario))

    db.commit()
    db.close()
    return redirect("/")


# ---------------- VENTAS ----------------
@app.route("/finalizar_venta", methods=["POST"])
def finalizar_venta():
    db = get_db()

    data = json.loads(request.form["data"])
    cliente = data["cliente"]
    carrito = data["carrito"]

    cursor = db.cursor()

    cursor.execute("""
        INSERT INTO clientes (nombre, telefono, direccion)
        VALUES (?, ?, ?)
    """, (cliente["nombre"], cliente["telefono"], cliente["direccion"]))

    cliente_id = cursor.lastrowid

    total = 0

    for item in carrito:
        prod = db.execute("SELECT * FROM productos WHERE id=?", (item["id"],)).fetchone()

        subtotal = prod["precio"] * item["cantidad"]
        total += subtotal

        db.execute("""
            UPDATE productos
            SET stock = stock - ?
            WHERE id=?
        """, (item["cantidad"], item["id"]))

    db.execute("""
        INSERT INTO ventas (cliente_id, total)
        VALUES (?, ?)
    """, (cliente_id, total))

    db.commit()
    db.close()

    return jsonify({"ok": True})


# ---------------- CLIENTES ----------------
@app.route("/clientes")
def clientes():
    db = get_db()

    clientes = db.execute("""
        SELECT c.id, c.nombre,
        COALESCE(SUM(v.total),0) as total_comprado
        FROM clientes c
        LEFT JOIN ventas v ON v.cliente_id = c.id
        GROUP BY c.id
    """).fetchall()

    db.close()
    return render_template("clientes.html", clientes=clientes)


# ---------------- BOLETAS ----------------
@app.route("/boletas")
def boletas():
    db = get_db()

    boletas = db.execute("""
        SELECT * FROM ventas ORDER BY id DESC
    """).fetchall()

    db.close()
    return render_template("boletas.html", boletas=boletas)


# ---------------- DASHBOARD ----------------
@app.route("/dashboard")
def dashboard():
    db = get_db()

    total_ventas = db.execute("SELECT SUM(total) FROM ventas").fetchone()[0] or 0
    total_compras = db.execute("SELECT SUM(total) FROM compras").fetchone()[0] or 0
    ventas = db.execute("SELECT COUNT(*) FROM ventas").fetchone()[0]

    ganancia = total_ventas - total_compras

    db.close()

    return render_template(
        "dashboard.html",
        total_ventas=total_ventas,
        total_compras=total_compras,
        ventas=ventas,
        ganancia=ganancia
    )


# ---------------- RUN ----------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
