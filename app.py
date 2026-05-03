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
    db.execute("""
        CREATE TABLE IF NOT EXISTS productos (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            nombre TEXT NOT NULL, precio REAL NOT NULL, stock INTEGER NOT NULL, 
            unidad TEXT DEFAULT 'Unidad', oferta TEXT DEFAULT ''
        )""")
    db.execute("""
        CREATE TABLE IF NOT EXISTS compras (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            lugar TEXT, direccion TEXT, producto TEXT, 
            cantidad INTEGER, total REAL, fecha TEXT DEFAULT (DATETIME('now','localtime'))
        )""")
    db.execute("""
        CREATE TABLE IF NOT EXISTS ventas (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            cliente TEXT, direccion TEXT, telefono TEXT, detalle TEXT, 
            total REAL, pagado REAL DEFAULT 0, saldo REAL DEFAULT 0, 
            estado TEXT DEFAULT 'fiado', fecha TEXT DEFAULT (DATETIME('now','localtime'))
        )""")
    db.commit()
    db.close()

init_db()

@app.route("/")
def index():
    db = get_db()
    rows = db.execute("SELECT * FROM productos ORDER BY nombre ASC").fetchall()
    productos = [dict(r) for r in rows]
    db.close()
    return render_template("index.html", productos=productos)

# --- PRODUCTOS: AGREGAR, EDITAR, ELIMINAR ---
@app.route("/agregar_producto", methods=["POST"])
def agregar_producto():
    db = get_db()
    db.execute("INSERT INTO productos (nombre, precio, stock, unidad, oferta) VALUES (?, ?, ?, ?, ?)", 
               (request.form['nombre'], float(request.form['precio']), int(request.form['stock']), 
                request.form.get('unidad', 'Unidad'), request.form.get('oferta', '')))
    db.commit()
    db.close()
    return redirect("/")

@app.route("/editar_producto", methods=["POST"])
def editar_producto():
    db = get_db()
    db.execute("UPDATE productos SET nombre=?, precio=?, stock=?, unidad=?, oferta=? WHERE id=?",
               (request.form['nombre'], float(request.form['precio']), int(request.form['stock']), 
                request.form['unidad'], request.form['oferta'], int(request.form['id'])))
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

# --- COMPRAS: ABASTECIMIENTO INTELIGENTE ---
@app.route("/compras")
def compras():
    db = get_db()
    historial = db.execute("SELECT * FROM compras ORDER BY id DESC").fetchall()
    productos = db.execute("SELECT nombre FROM productos ORDER BY nombre ASC").fetchall()
    db.close()
    return render_template("compras.html", historial=historial, productos=productos)

@app.route("/agregar_compra", methods=["POST"])
def agregar_compra():
    try:
        db = get_db()
        nombre_p = request.form['producto'].strip()
        cantidad = int(request.form['cantidad'])
        total_compra = float(request.form['total'])
        
        db.execute("INSERT INTO compras (lugar, direccion, producto, cantidad, total) VALUES (?, ?, ?, ?, ?)",
                   (request.form['lugar'], request.form['direccion'], nombre_p, cantidad, total_compra))

        p_existente = db.execute("SELECT id FROM productos WHERE nombre = ?", (nombre_p,)).fetchone()
        if p_existente:
            db.execute("UPDATE productos SET stock = stock + ? WHERE nombre = ?", (cantidad, nombre_p))
        else:
            # Crea el producto nuevo si no existe
            precio_base = (total_compra / cantidad) * 1.30
            db.execute("INSERT INTO productos (nombre, precio, stock, unidad) VALUES (?, ?, ?, ?)",
                       (nombre_p, round(precio_base, 2), cantidad, 'Unidad'))
        db.commit()
        db.close()
        return redirect("/compras")
    except Exception as e:
        return f"Error en compra: {e}", 500

# --- VENTAS Y COBRANZAS ---
@app.route("/vender")
def vender():
    return render_template("ventas.html")

@app.route("/productos_json")
def productos_json():
    db = get_db()
    productos = db.execute("SELECT id, nombre, precio, stock, unidad, oferta FROM productos").fetchall()
    db.close()
    return jsonify([dict(p) for p in productos])

@app.route("/finalizar_venta", methods=["POST"])
def finalizar_venta():
    db = get_db()
    data = json.loads(request.form["data"])
    total_v = 0
    detalle = []
    for item in data["carrito"]:
        p = db.execute("SELECT * FROM productos WHERE id=?", (item["id"],)).fetchone()
        if p:
            sub = p["precio"] * item["cantidad"]
            total_v += sub
            detalle.append({"nombre": p["nombre"], "cantidad": item["cantidad"], "precio": p["precio"], "subtotal": sub})
            db.execute("UPDATE productos SET stock = stock - ? WHERE id=?", (item["cantidad"], item["id"]))
    
    db.execute("INSERT INTO ventas (cliente, direccion, telefono, detalle, total, pagado, saldo, estado) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
               (data["cliente"]["nombre"], data["cliente"]["direccion"], data["cliente"]["telefono"], json.dumps(detalle), total_v, 0, total_v, "fiado"))
    db.commit()
    db.close()
    return jsonify({"ok": True})

@app.route("/boletas")
def boletas():
    db = get_db()
    res = db.execute("SELECT * FROM ventas ORDER BY id DESC").fetchall()
    db.close()
    return render_template("boletas.html", boletas=res)

@app.route("/registrar_pago", methods=["POST"])
def registrar_pago():
    db = get_db()
    id_v = request.form['id']
    monto = float(request.form['monto'])
    v = db.execute("SELECT total, pagado FROM ventas WHERE id=?", (id_v,)).fetchone()
    nuevo_p = v['pagado'] + monto
    nuevo_s = v['total'] - nuevo_p
    est = "pagado" if nuevo_s <= 0 else "parcial"
    db.execute("UPDATE ventas SET pagado=?, saldo=?, estado=? WHERE id=?", (nuevo_p, max(0, nuevo_s), est, id_v))
    db.commit()
    db.close()
    return redirect("/boletas")

@app.route("/clientes")
def clientes():
    db = get_db()
    res = db.execute("SELECT cliente, direccion, telefono, SUM(total) as total_gastado, SUM(saldo) as deuda_total, COUNT(id) as total_compras FROM ventas GROUP BY cliente ORDER BY deuda_total DESC").fetchall()
    db.close()
    return render_template("clientes.html", clientes=res)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
