from flask import Flask, render_template, request, redirect, jsonify
import sqlite3
import json
import os

app = Flask(__name__)
app.jinja_env.filters['fromjson'] = json.loads

def get_db():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(base_dir, "db.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    db = get_db()
    db.execute("""CREATE TABLE IF NOT EXISTS productos (
        id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT, precio REAL, 
        stock INTEGER, unidad TEXT DEFAULT 'Unidad', oferta TEXT DEFAULT ''
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS compras (
        id INTEGER PRIMARY KEY AUTOINCREMENT, lugar TEXT, producto TEXT, 
        cantidad INTEGER, total REAL, fecha TEXT DEFAULT (DATETIME('now','localtime'))
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS ventas (
        id INTEGER PRIMARY KEY AUTOINCREMENT, cliente TEXT, direccion TEXT, 
        whatsapp TEXT, detalle TEXT, total REAL, pagado REAL DEFAULT 0, 
        saldo REAL DEFAULT 0, estado TEXT DEFAULT 'fiado', 
        fecha TEXT DEFAULT (DATETIME('now','localtime'))
    )""")
    db.commit()
    db.close()

init_db()

@app.route("/")
def index():
    db = get_db()
    prods = db.execute("SELECT * FROM productos ORDER BY nombre ASC").fetchall()
    db.close()
    return render_template("index.html", productos=prods)

@app.route("/agregar_producto", methods=["POST"])
def agregar_producto():
    db = get_db()
    db.execute("INSERT INTO productos (nombre, precio, stock, unidad, oferta) VALUES (?,?,?,?,?)",
               (request.form['nombre'], float(request.form['precio']), int(request.form['stock']), 
                request.form['unidad'], request.form['oferta']))
    db.commit()
    db.close()
    return redirect("/")

@app.route("/vender")
def vender():
    return render_template("ventas.html")

@app.route("/productos_json")
def productos_json():
    db = get_db()
    res = db.execute("SELECT * FROM productos WHERE stock > 0").fetchall()
    db.close()
    return jsonify([dict(r) for r in res])

@app.route("/finalizar_venta", methods=["POST"])
def finalizar_venta():
    db = get_db()
    data = request.json
    c, carrito = data["cliente"], data["carrito"]
    total = sum(float(i['precio']) * int(i['cantidad']) for i in carrito)
    db.execute("INSERT INTO ventas (cliente, direccion, whatsapp, detalle, total, saldo) VALUES (?,?,?,?,?,?)",
               (c['nombre'], c.get('direccion',''), c.get('whatsapp',''), json.dumps(carrito), total, total))
    for item in carrito:
        db.execute("UPDATE productos SET stock = stock - ? WHERE id = ?", (item['cantidad'], item['id']))
    db.commit()
    db.close()
    return jsonify({"ok": True})

@app.route("/compras")
def compras_page():
    db = get_db()
    hist = db.execute("SELECT * FROM compras ORDER BY id DESC LIMIT 15").fetchall()
    prods = db.execute("SELECT nombre FROM productos").fetchall()
    db.close()
    return render_template("compras.html", historial=hist, productos=prods)

@app.route("/agregar_compra", methods=["POST"])
def agregar_compra():
    db = get_db()
    try:
        prod_nombre = request.form['producto'].strip()
        cant, costo = int(request.form['cantidad']), float(request.form['total'])
        lugar = request.form.get('lugar', 'Proveedor')
        # Si el producto no existe, lo crea
        existe = db.execute("SELECT id FROM productos WHERE nombre = ?", (prod_nombre,)).fetchone()
        if not existe:
            db.execute("INSERT INTO productos (nombre, precio, stock) VALUES (?, 0, 0)", (prod_nombre,))
        db.execute("INSERT INTO compras (lugar, producto, cantidad, total) VALUES (?,?,?,?)", (lugar, prod_nombre, cant, costo))
        db.execute("UPDATE productos SET stock = stock + ? WHERE nombre = ?", (cant, prod_nombre))
        db.commit()
    except: pass
    finally: db.close()
    return redirect("/compras")

@app.route("/boletas")
def boletas():
    db = get_db()
    res = db.execute("SELECT * FROM ventas ORDER BY id DESC").fetchall()
    db.close()
    return render_template("boletas.html", boletas=res)

@app.route("/registrar_pago", methods=["POST"])
def registrar_pago():
    db = get_db()
    id_v, monto = request.form['id'], float(request.form['monto'])
    v = db.execute("SELECT total, pagado FROM ventas WHERE id=?", (id_v,)).fetchone()
    nuevo_pago = v['pagado'] + monto
    nuevo_saldo = max(0, v['total'] - nuevo_pago)
    db.execute("UPDATE ventas SET pagado=?, saldo=?, estado=? WHERE id=?", 
               (nuevo_pago, nuevo_saldo, ("pagado" if nuevo_saldo <= 0 else "parcial"), id_v))
    db.commit()
    db.close()
    return redirect("/boletas")

@app.route("/dashboard")
def dashboard():
    db = get_db()
    v = db.execute("SELECT SUM(total) FROM ventas").fetchone()[0] or 0
    c = db.execute("SELECT SUM(total) FROM compras").fetchone()[0] or 0
    db.close()
    return render_template("dashboard.html", total_ventas=v, total_compras=c, ganancia=v-c)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000, debug=True)
