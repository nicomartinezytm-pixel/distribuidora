from flask import Flask, render_template, request, redirect, jsonify
import sqlite3
import json
import os

app = Flask(__name__)

# -------- DB --------
def get_db():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    conn = sqlite3.connect(os.path.join(base_dir, "db.db"))
    conn.row_factory = sqlite3.Row
    return conn


# -------- INIT DB --------
def init_db():
    db = get_db()

    db.execute("""
    CREATE TABLE IF NOT EXISTS productos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT,
        precio REAL,
        stock INTEGER,
        tipo_precio TEXT,
        extra INTEGER DEFAULT 1
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
    CREATE TABLE IF NOT EXISTS detalle_venta (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        venta_id INTEGER,
        producto_id INTEGER,
        cantidad INTEGER
    )
    """)

    db.commit()
    db.close()


with app.app_context():
    init_db()


# -------- HOME --------
@app.route("/")
def index():
    db = get_db()
    productos = db.execute("SELECT * FROM productos").fetchall()
    db.close()
    return render_template("index.html", productos=productos)


# -------- PRODUCTOS --------
@app.route("/agregar_producto", methods=["POST"])
def agregar_producto():
    db = get_db()

    tipo = request.form["tipo_precio"]
    extra = 1

    if tipo == "cantidad":
        extra = int(request.form.get("cantidad_extra") or 1)
    elif tipo == "oferta":
        extra = int(request.form.get("oferta_unidades") or 1)

    db.execute("""
        INSERT INTO productos (nombre, precio, stock, tipo_precio, extra)
        VALUES (?, ?, ?, ?, ?)
    """, (
        request.form["nombre"],
        float(request.form["precio"]),
        int(request.form["stock"]),
        tipo,
        extra
    ))

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


# -------- PRODUCTOS JSON (FIX CLAVE) --------
@app.route("/productos_json")
def productos_json():
    db = get_db()
    productos = db.execute("SELECT * FROM productos").fetchall()
    db.close()

    lista = []

    for p in productos:
        lista.append({
            "id": p["id"],
            "nombre": p["nombre"],
            "precio": float(p["precio"]),
            "stock": p["stock"],
            "tipo_precio": p["tipo_precio"]
        })

    return jsonify(lista)


# -------- VENTAS --------
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
    """, (
        cliente["nombre"],
        cliente["telefono"],
        cliente["direccion"]
    ))

    cliente_id = cursor.lastrowid

    cursor.execute("""
        INSERT INTO ventas (cliente_id, total)
        VALUES (?, ?)
    """, (cliente_id, 0))

    venta_id = cursor.lastrowid

    total = 0

    for item in carrito:

        prod = db.execute("""
            SELECT precio FROM productos WHERE id=?
        """, (item["id"],)).fetchone()

        subtotal = prod["precio"] * item["cantidad"]
        total += subtotal

        db.execute("""
            INSERT INTO detalle_venta (venta_id, producto_id, cantidad)
            VALUES (?, ?, ?)
        """, (venta_id, item["id"], item["cantidad"]))

        db.execute("""
            UPDATE productos
            SET stock = stock - ?
            WHERE id = ?
        """, (item["cantidad"], item["id"]))

    db.execute("UPDATE ventas SET total=? WHERE id=?", (total, venta_id))

    db.commit()
    db.close()

    return jsonify({"ok": True})


# -------- DASHBOARD --------
@app.route("/dashboard")
def dashboard():
    db = get_db()

    total = db.execute("SELECT SUM(total) FROM ventas").fetchone()[0] or 0
    ventas = db.execute("SELECT COUNT(*) FROM ventas").fetchone()[0]

    ranking = db.execute("""
        SELECT clientes.nombre, SUM(ventas.total)
        FROM ventas
        JOIN clientes ON ventas.cliente_id = clientes.id
        GROUP BY clientes.id
        ORDER BY SUM(ventas.total) DESC
    """).fetchall()

    nombres = [r[0] for r in ranking]
    totales = [r[1] for r in ranking]

    db.close()

    return render_template("dashboard.html",
                           total=total,
                           ventas=ventas,
                           nombres=nombres,
                           totales=totales)


# -------- GANANCIAS --------
@app.route("/ganancias")
def ganancias():
    db = get_db()

    total_dia = db.execute("""
        SELECT SUM(total)
        FROM ventas
        WHERE fecha = DATE('now')
    """).fetchone()[0] or 0

    ventas_dia = db.execute("""
        SELECT COUNT(*)
        FROM ventas
        WHERE fecha = DATE('now')
    """).fetchone()[0]

    clientes = db.execute("""
        SELECT clientes.nombre, SUM(ventas.total)
        FROM ventas
        JOIN clientes ON ventas.cliente_id = clientes.id
        GROUP BY clientes.id
        ORDER BY SUM(ventas.total) DESC
    """).fetchall()

    db.close()

    return render_template("ganancias.html",
                           total_dia=total_dia,
                           ventas_dia=ventas_dia,
                           clientes=clientes)


# -------- RUN --------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
