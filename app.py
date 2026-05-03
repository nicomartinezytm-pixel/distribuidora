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
        stock INTEGER,
        tipo_precio TEXT,
        unidades INTEGER DEFAULT 1,
        oferta_unidades INTEGER DEFAULT 1
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
        fecha TEXT DEFAULT (DATE('now'))
    )
    """)

    db.execute("""
    CREATE TABLE IF NOT EXISTS boletas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cliente_id INTEGER,
        total REAL,
        pagado REAL DEFAULT 0,
        estado TEXT DEFAULT 'pendiente',
        fecha TEXT DEFAULT (DATE('now')),
        vencimiento TEXT
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
    tipo = request.form["tipo_precio"]

    unidades = 1
    oferta_unidades = 1

    if tipo == "cantidad":
        unidades = int(request.form.get("unidades") or 1)

    if tipo == "oferta":
        oferta_unidades = int(request.form.get("oferta_unidades") or 1)

    db.execute("""
        INSERT INTO productos (nombre, precio, stock, tipo_precio, unidades, oferta_unidades)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (nombre, precio, stock, tipo, unidades, oferta_unidades))

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
    return render_template("ventas.html")


@app.route("/finalizar_venta", methods=["POST"])
def finalizar_venta():
    db = get_db()

    data = json.loads(request.form["data"])
    cliente = data["cliente"]
    carrito = data["carrito"]

    cursor = db.cursor()

    # crear cliente SIEMPRE
    cursor.execute("""
        INSERT INTO clientes (nombre, telefono, direccion)
        VALUES (?, ?, ?)
    """, (cliente["nombre"], cliente["telefono"], cliente["direccion"]))

    cliente_id = cursor.lastrowid

    total = 0

    for item in carrito:
        prod = db.execute("SELECT precio FROM productos WHERE id=?", (item["id"],)).fetchone()
        subtotal = prod["precio"] * item["cantidad"]
        total += subtotal

        db.execute("""
            UPDATE productos
            SET stock = stock - ?
            WHERE id=?
        """, (item["cantidad"], item["id"]))

    # 🔥 esto alimenta la cuenta corriente
    db.execute("""
        INSERT INTO ventas (cliente_id, total)
        VALUES (?, ?)
    """, (cliente_id, total))

    db.commit()
    db.close()

    return jsonify({"ok": True})


# ---------------- CUENTA CORRIENTE CLIENTES ----------------
@app.route("/clientes")
def clientes():
    db = get_db()

    clientes = db.execute("""
        SELECT c.id, c.nombre,
        COALESCE(SUM(v.total), 0) as total_comprado
        FROM clientes c
        LEFT JOIN ventas v ON v.cliente_id = c.id
        GROUP BY c.id
    """).fetchall()

    deudas = db.execute("""
        SELECT c.nombre,
        SUM(b.total - b.pagado) as deuda
        FROM boletas b
        JOIN clientes c ON c.id = b.cliente_id
        WHERE b.estado='pendiente'
        GROUP BY c.id
        ORDER BY deuda DESC
    """).fetchall()

    db.close()

    return render_template("clientes.html", clientes=clientes, deudas=deudas)


# ---------------- DASHBOARD ----------------
@app.route("/dashboard")
def dashboard():
    db = get_db()

    total = db.execute("SELECT SUM(total) FROM ventas").fetchone()[0] or 0
    ventas = db.execute("SELECT COUNT(*) FROM ventas").fetchone()[0]

    ranking = db.execute("""
        SELECT clientes.nombre, SUM(ventas.total) as total
        FROM ventas
        JOIN clientes ON clientes.id = ventas.cliente_id
        GROUP BY clientes.id
        ORDER BY total DESC
        LIMIT 5
    """).fetchall()

    db.close()

    return render_template("dashboard.html",
                           total=total,
                           ventas=ventas,
                           ranking=ranking)


# ---------------- RUN ----------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
