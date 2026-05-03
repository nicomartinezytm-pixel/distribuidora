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


# ---------------- INIT ----------------
def init_db():
    db = get_db()

    db.execute("""
    CREATE TABLE IF NOT EXISTS productos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT,
        precio REAL,
        stock INTEGER,
        tipo TEXT DEFAULT 'unidad',
        oferta TEXT DEFAULT ''
    )
    """)

    db.execute("""
    CREATE TABLE IF NOT EXISTS ventas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cliente TEXT,
        direccion TEXT,
        total REAL,
        fecha TEXT DEFAULT (DATETIME('now','localtime'))
    )
    """)

    db.execute("""
    CREATE TABLE IF NOT EXISTS compras (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lugar TEXT,
        producto TEXT,
        cantidad INTEGER,
        total REAL,
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


# ---------------- VENTAS ----------------
@app.route("/vender")
def vender():
    db = get_db()
    productos = db.execute("SELECT * FROM productos").fetchall()
    db.close()
    return render_template("ventas.html", productos=productos)


@app.route("/finalizar_venta", methods=["POST"])
def finalizar_venta():
    db = get_db()

    data = json.loads(request.form["data"])
    cliente = data["cliente"]
    carrito = data["carrito"]

    total = 0

    for item in carrito:
        prod = db.execute("SELECT * FROM productos WHERE id=?", (item["id"],)).fetchone()

        if prod:
            subtotal = prod["precio"] * item["cantidad"]
            total += subtotal

            db.execute("""
                UPDATE productos
                SET stock = stock - ?
                WHERE id=?
            """, (item["cantidad"], item["id"]))

    db.execute("""
        INSERT INTO ventas (cliente, direccion, total)
        VALUES (?, ?, ?)
    """, (cliente["nombre"], cliente["direccion"], total))

    db.commit()
    db.close()

    return jsonify({"ok": True})


# ---------------- COMPRAS ----------------
@app.route("/agregar_compra", methods=["POST"])
def agregar_compra():
    db = get_db()

    lugar = request.form["lugar"]
    producto = request.form["producto"]
    cantidad = int(request.form["cantidad"])
    total = float(request.form["total"])

    db.execute("""
        INSERT INTO compras (lugar, producto, cantidad, total)
        VALUES (?, ?, ?, ?)
    """, (lugar, producto, cantidad, total))

    db.commit()
    db.close()
    return redirect("/")


# ---------------- CLIENTES ----------------
@app.route("/clientes")
def clientes():
    db = get_db()

    clientes = db.execute("""
        SELECT cliente, SUM(total) as total
        FROM ventas
        GROUP BY cliente
    """).fetchall()

    db.close()
    return render_template("clientes.html", clientes=clientes)


# ---------------- DASHBOARD ----------------
@app.route("/dashboard")
def dashboard():
    db = get_db()

    ventas = db.execute("SELECT SUM(total) FROM ventas").fetchone()[0] or 0
    compras = db.execute("SELECT SUM(total) FROM compras").fetchone()[0] or 0
    ganancia = ventas - compras

    db.close()

    return render_template(
        "dashboard.html",
        ventas=ventas,
        compras=compras,
        ganancia=ganancia
    )


# ---------------- GANANCIAS ----------------
@app.route("/ganancias")
def ganancias():
    db = get_db()

    ventas = db.execute("SELECT SUM(total) FROM ventas").fetchone()[0] or 0
    compras = db.execute("SELECT SUM(total) FROM compras").fetchone()[0] or 0

    db.close()

    return render_template("ganancias.html", ventas=ventas, compras=compras)


# ---------------- RUN ----------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
