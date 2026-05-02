from flask import Flask, render_template, request, redirect
import sqlite3
import json
import os

app = Flask(__name__)

# -------- DB --------
def get_db():
    path = os.path.join(os.getcwd(), "db.db")
    return sqlite3.connect(path)

# 🔥 CREAR TABLAS AUTOMÁTICO (CLAVE PARA RENDER)
db = get_db()

db.execute("CREATE TABLE IF NOT EXISTS productos (id INTEGER PRIMARY KEY, nombre TEXT, precio REAL, stock INTEGER, tipo_precio TEXT)")
db.execute("CREATE TABLE IF NOT EXISTS clientes (id INTEGER PRIMARY KEY, nombre TEXT, telefono TEXT, direccion TEXT)")
db.execute("CREATE TABLE IF NOT EXISTS ventas (id INTEGER PRIMARY KEY AUTOINCREMENT, cliente_id INTEGER, total REAL)")
db.execute("CREATE TABLE IF NOT EXISTS detalle_venta (id INTEGER PRIMARY KEY AUTOINCREMENT, venta_id INTEGER, producto_id INTEGER, cantidad INTEGER)")

db.commit()

# -------- HOME --------
@app.route("/")
def index():
    db = get_db()
    productos = db.execute("SELECT * FROM productos").fetchall()
    clientes = db.execute("SELECT * FROM clientes").fetchall()
    return render_template("index.html", productos=productos, clientes=clientes)

# -------- PRODUCTOS --------
@app.route("/agregar_producto", methods=["POST"])
def agregar_producto():
    db = get_db()
    db.execute("INSERT INTO productos (nombre, precio, stock, tipo_precio) VALUES (?, ?, ?, ?)",
               (request.form["nombre"], request.form["precio"], request.form["stock"], request.form["tipo_precio"]))
    db.commit()
    return redirect("/")

@app.route("/eliminar_producto/<int:id>")
def eliminar_producto(id):
    db = get_db()
    db.execute("DELETE FROM productos WHERE id=?", (id,))
    db.commit()
    return redirect("/")

@app.route("/editar_producto/<int:id>", methods=["POST"])
def editar_producto(id):
    db = get_db()
    db.execute("UPDATE productos SET nombre=?, precio=?, stock=?, tipo_precio=? WHERE id=?",
               (request.form["nombre"], request.form["precio"], request.form["stock"], request.form["tipo_precio"], id))
    db.commit()
    return redirect("/")

# -------- CLIENTES --------
@app.route("/agregar_cliente", methods=["POST"])
def agregar_cliente():
    db = get_db()
    db.execute("INSERT INTO clientes (nombre, telefono, direccion) VALUES (?, ?, ?)",
               (request.form["nombre"], request.form["telefono"], request.form["direccion"]))
    db.commit()
    return redirect("/")

# -------- VENTAS --------
@app.route("/vender")
def vender():
    db = get_db()
    productos = db.execute("SELECT * FROM productos").fetchall()
    clientes = db.execute("SELECT * FROM clientes").fetchall()
    return render_template("ventas.html", productos=productos, clientes=clientes)

@app.route("/finalizar_venta", methods=["POST"])
def finalizar_venta():
    db = get_db()

    cliente_id = request.form["cliente"]
    total = float(request.form["total"])
    carrito = json.loads(request.form["carrito"])

    cursor = db.cursor()
    cursor.execute("INSERT INTO ventas (cliente_id, total) VALUES (?, ?)", (cliente_id, total))
    venta_id = cursor.lastrowid

    for item in carrito:
        db.execute("INSERT INTO detalle_venta (venta_id, producto_id, cantidad) VALUES (?, ?, ?)",
                   (venta_id, item["id"], item["cantidad"]))

        db.execute("UPDATE productos SET stock = stock - ? WHERE id = ?",
                   (item["cantidad"], item["id"]))

    db.commit()
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

    return render_template("dashboard.html",
                           total=total,
                           ventas=ventas,
                           ranking=ranking,
                           nombres=nombres,
                           totales=totales)
