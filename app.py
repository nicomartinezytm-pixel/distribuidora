from flask import Flask, render_template, request, redirect
import sqlite3
import json
import os

app = Flask(__name__)

# -------- DB --------
def get_db():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base_dir, "db.db")
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


# -------- INIT DB (CREA TODO SOLO) --------
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
        total REAL
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


# ejecutar al iniciar servidor
with app.app_context():
    init_db()


# -------- HOME --------
@app.route("/")
def index():
    db = get_db()
    productos = db.execute("SELECT * FROM productos").fetchall()
    clientes = db.execute("SELECT * FROM clientes").fetchall()
    db.close()
    return render_template("index.html", productos=productos, clientes=clientes)


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
        request.form["precio"],
        request.form["stock"],
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
        request.form["precio"],
        request.form["stock"],
        request.form["tipo_precio"],
        id
    ))

    db.commit()
    db.close()
    return redirect("/")


# -------- CLIENTES --------
@app.route("/agregar_cliente", methods=["POST"])
def agregar_cliente():
    db = get_db()

    db.execute("""
        INSERT INTO clientes (nombre, telefono, direccion)
        VALUES (?, ?, ?)
    """, (
        request.form["nombre"],
        request.form["telefono"],
        request.form["direccion"]
    ))

    db.commit()
    db.close()
    return redirect("/")


# -------- VENTAS --------
@app.route("/vender")
def vender():
    db = get_db()
    productos = db.execute("SELECT * FROM productos").fetchall()
    clientes = db.execute("SELECT * FROM clientes").fetchall()
    db.close()
    return render_template("ventas.html", productos=productos, clientes=clientes)


@app.route("/finalizar_venta", methods=["POST"])
def finalizar_venta():
    db = get_db()

    nombre = request.form["cliente_nombre"]
    telefono = request.form["cliente_telefono"]
    direccion = request.form["cliente_direccion"]

    carrito = json.loads(request.form["carrito"])

    cursor = db.cursor()

    # crear cliente
    cursor.execute("""
        INSERT INTO clientes (nombre, telefono, direccion)
        VALUES (?, ?, ?)
    """, (nombre, telefono, direccion))

    cliente_id = cursor.lastrowid

    # crear venta
    cursor.execute("""
        INSERT INTO ventas (cliente_id, total)
        VALUES (?, ?)
    """, (cliente_id, 0))

    venta_id = cursor.lastrowid

    total = 0

    for item in carrito:
        prod = db.execute("""
            SELECT precio, tipo_precio, extra
            FROM productos WHERE id=?
        """, (item["id"],)).fetchone()

        precio = prod["precio"]
        tipo = prod["tipo_precio"]
        extra = prod["extra"]

        cantidad = item["cantidad"]

        # 🔥 LÓGICA DE PRECIOS
        if tipo == "unidad":
            subtotal = precio * cantidad

        elif tipo == "cantidad":
            subtotal = precio * cantidad * extra

        elif tipo == "oferta":
            subtotal = (precio * cantidad * extra) * 0.9

        else:
            subtotal = precio * cantidad

        total += subtotal

        db.execute("""
            INSERT INTO detalle_venta (venta_id, producto_id, cantidad)
            VALUES (?, ?, ?)
        """, (venta_id, item["id"], cantidad))

        db.execute("""
            UPDATE productos
            SET stock = stock - ?
            WHERE id = ?
        """, (cantidad, item["id"]))

    db.execute("UPDATE ventas SET total=? WHERE id=?", (total, venta_id))

    db.commit()
    db.close()

    return redirect("/")


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

    return render_template(
        "dashboard.html",
        total=total,
        ventas=ventas,
        ranking=ranking,
        nombres=nombres,
        totales=totales
    )


# -------- RUN --------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
