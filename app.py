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
        unidades INTEGER DEFAULT 1
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


# ---------------- PRODUCTOS JSON ----------------
@app.route("/productos_json")
def productos_json():
    db = get_db()
    productos = db.execute("SELECT * FROM productos").fetchall()
    db.close()
    return jsonify([dict(p) for p in productos])


# ---------------- AGREGAR PRODUCTO (AQUÍ ESTÁ TODO LO NUEVO BIEN) ----------------
@app.route("/agregar_producto", methods=["POST"])
def agregar_producto():
    db = get_db()

    nombre = request.form["nombre"]
    precio = float(request.form["precio"])
    stock = int(request.form["stock"])
    tipo = request.form["tipo_precio"]

    # 🔥 lógica nueva
    if tipo == "unidad":
        unidades = 1

    elif tipo == "cantidad":
        # ej: pack de 6 unidades
        unidades = int(request.form.get("unidades", 1))

    elif tipo == "oferta":
        # ej: 2x1 / 3x2 etc
        unidades = int(request.form.get("unidades_oferta", 1))

    else:
        unidades = 1

    db.execute("""
        INSERT INTO productos (nombre, precio, stock, tipo_precio, unidades)
        VALUES (?, ?, ?, ?, ?)
    """, (nombre, precio, stock, tipo, unidades))

    db.commit()
    db.close()
    return redirect("/")


# ---------------- ELIMINAR ----------------
@app.route("/eliminar_producto/<int:id>")
def eliminar_producto(id):
    db = get_db()
    db.execute("DELETE FROM productos WHERE id=?", (id,))
    db.commit()
    db.close()
    return redirect("/")


# ---------------- EDITAR ----------------
@app.route("/editar_producto/<int:id>", methods=["POST"])
def editar_producto(id):
    db = get_db()

    db.execute("""
        UPDATE productos
        SET nombre=?, precio=?, stock=?, tipo_precio=?
        WHERE id=?
    """, (
        request.form["nombre"],
        float(request.form["precio"]),
        int(request.form["stock"]),
        request.form["tipo_precio"],
        id
    ))

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

    db.execute("""
        INSERT INTO ventas (cliente_id, total)
        VALUES (?, ?)
    """, (cliente_id, total))

    db.commit()
    db.close()

    return jsonify({"ok": True})


# ---------------- BOLETAS ----------------
@app.route("/boletas")
def boletas():
    db = get_db()

    boletas = db.execute("""
        SELECT boletas.*, clientes.nombre
        FROM boletas
        JOIN clientes ON clientes.id = boletas.cliente_id
    """).fetchall()

    alertas = db.execute("""
        SELECT clientes.nombre, COUNT(*) as atrasos
        FROM boletas
        JOIN clientes ON clientes.id = boletas.cliente_id
        WHERE boletas.estado='pendiente'
        GROUP BY clientes.id
        HAVING atrasos >= 3
    """).fetchall()

    db.close()

    return render_template("boletas.html", boletas=boletas, alertas=alertas)


@app.route("/pagar_boleta/<int:id>", methods=["POST"])
def pagar_boleta(id):
    db = get_db()

    pago = float(request.form["pagado"])

    boleta = db.execute("SELECT * FROM boletas WHERE id=?", (id,)).fetchone()

    nuevo_pagado = boleta["pagado"] + pago
    estado = "pagado" if nuevo_pagado >= boleta["total"] else "pendiente"

    db.execute("""
        UPDATE boletas
        SET pagado=?, estado=?
        WHERE id=?
    """, (nuevo_pagado, estado, id))

    db.commit()
    db.close()

    return redirect("/boletas")


# ---------------- DASHBOARD ----------------
@app.route("/dashboard")
def dashboard():
    db = get_db()

    total = db.execute("SELECT SUM(total) FROM ventas").fetchone()[0] or 0
    ventas = db.execute("SELECT COUNT(*) FROM ventas").fetchone()[0]

    boletas_pendientes = db.execute("""
        SELECT COUNT(*) FROM boletas WHERE estado='pendiente'
    """).fetchone()[0]

    deuda_total = db.execute("""
        SELECT SUM(total - pagado)
        FROM boletas
        WHERE estado='pendiente'
    """).fetchone()[0] or 0

    db.close()

    return render_template("dashboard.html",
                           total=total,
                           ventas=ventas,
                           boletas_pendientes=boletas_pendientes,
                           deuda_total=deuda_total)


# ---------------- RUN ----------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
