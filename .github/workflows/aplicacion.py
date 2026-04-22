from flask import Flask, render_template, request, redirect, url_for, flash, g
from datetime import datetime, date, timedelta
import sqlite3, os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'joyeria-secreta-2024'
DATABASE = os.path.join(os.path.dirname(__file__), 'joyeria.db')

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None: db.close()

def query(sql, args=(), one=False):
    cur = get_db().execute(sql, args)
    rv = cur.fetchall()
    return (rv[0] if rv else None) if one else rv

def execute(sql, args=()):
    db = get_db()
    cur = db.execute(sql, args)
    db.commit()
    return cur.lastrowid

def init_db():
    db = sqlite3.connect(DATABASE)
    db.executescript("""
    PRAGMA foreign_keys = ON;
    CREATE TABLE IF NOT EXISTS cliente (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL, apellido TEXT NOT NULL,
        telefono TEXT, email TEXT, direccion TEXT,
        identificacion TEXT UNIQUE, notas TEXT,
        fecha_registro TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS joya (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        descripcion TEXT NOT NULL, tipo TEXT, material TEXT,
        quilates TEXT, peso_gramos REAL, valor_estimado REAL,
        origen TEXT DEFAULT 'propia', estado TEXT DEFAULT 'disponible',
        notas TEXT, fecha_ingreso TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS empenio (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        folio TEXT UNIQUE NOT NULL,
        cliente_id INTEGER NOT NULL REFERENCES cliente(id),
        joya_id INTEGER NOT NULL REFERENCES joya(id),
        monto_prestamo REAL NOT NULL, tasa_interes REAL DEFAULT 10.0,
        fecha_inicio TEXT NOT NULL, fecha_vencimiento TEXT,
        estado TEXT DEFAULT 'activo', notas TEXT
    );
    CREATE TABLE IF NOT EXISTS pago (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        empenio_id INTEGER NOT NULL REFERENCES empenio(id),
        monto REAL NOT NULL, tipo TEXT DEFAULT 'interes',
        fecha TEXT DEFAULT (datetime('now')), notas TEXT
    );
    """)
    db.commit(); db.close()

def generar_folio():
    row = query("SELECT MAX(id) as m FROM empenio", one=True)
    num = (row['m'] + 1) if row and row['m'] else 1
    return f"EMP-{num:05d}"

def calcular_interes(monto, tasa, fecha_inicio_str):
    try:
        fi = datetime.strptime(str(fecha_inicio_str)[:10], '%Y-%m-%d').date()
    except: return 0
    dias = (date.today() - fi).days
    return round(monto * (tasa / 100) * (dias / 30), 2)

def total_pagado(eid):
    r = query("SELECT COALESCE(SUM(monto),0) as t FROM pago WHERE empenio_id=?", (eid,), one=True)
    return r['t'] if r else 0

@app.template_filter('fecha')
def formato_fecha(valor):
    """Convierte cualquier fecha a formato DD/MM/YYYY"""
    if valor is None:
        return ''
    
    # Si ya es string pero en formato YYYY-MM-DD
    if isinstance(valor, str):
        try:
            # Intenta convertir de YYYY-MM-DD a datetime
            fecha = datetime.strptime(valor, '%Y-%m-%d')
            return fecha.strftime('%d/%m/%Y')
        except:
            # Si no puede convertir, devuelve el string original
            return valor
    
    # Si es objeto datetime o date
    if hasattr(valor, 'strftime'):
        return valor.strftime('%d/%m/%Y')
    
    return str(valor)


@app.route('/')
def dashboard():
    hoy = date.today().isoformat()
    total_clientes = query("SELECT COUNT(*) as c FROM cliente", one=True)['c']
    empenios_activos = query("SELECT COUNT(*) as c FROM empenio WHERE estado='activo'", one=True)['c']
    empenios_vencidos = query("SELECT COUNT(*) as c FROM empenio WHERE estado='activo' AND fecha_vencimiento < ?", (hoy,), one=True)['c']
    joyas_en_guarda = query("SELECT COUNT(*) as c FROM joya WHERE estado='empenada'", one=True)['c']
    primer_dia = date.today().replace(day=1).isoformat()
    ingresos_mes = query("SELECT COALESCE(SUM(monto),0) as t FROM pago WHERE fecha >= ?", (primer_dia,), one=True)['t']
    proximos = query("""SELECT e.*, c.nombre||' '||c.apellido as cliente_nombre, c.telefono
                        FROM empenio e JOIN cliente c ON e.cliente_id=c.id
                        WHERE e.estado='activo' AND e.fecha_vencimiento >= ? AND e.fecha_vencimiento <= ?
                        ORDER BY e.fecha_vencimiento""",
                     (hoy, (date.today()+timedelta(days=7)).isoformat()))
    ultimos = query("""SELECT e.*, c.nombre||' '||c.apellido as cliente_nombre
                       FROM empenio e JOIN cliente c ON e.cliente_id=c.id
                       ORDER BY e.id DESC LIMIT 6""")
    return render_template('dashboard.html', total_clientes=total_clientes,
        empenios_activos=empenios_activos, empenios_vencidos=empenios_vencidos,
        joyas_en_guarda=joyas_en_guarda, ingresos_mes=ingresos_mes,
        proximos=proximos, ultimos_empenios=ultimos, hoy=hoy)

@app.route('/clientes')
def clientes():
    q = request.args.get('q','')
    if q:
        like = f'%{q}%'
        rows = query("""SELECT c.*, c.nombre||' '||c.apellido as nombre_completo, COUNT(e.id) as total_emp, SUM(CASE WHEN e.estado='activo' THEN 1 ELSE 0 END) as activos
                        FROM cliente c LEFT JOIN empenio e ON e.cliente_id=c.id
                        WHERE c.nombre LIKE ? OR c.apellido LIKE ? OR c.identificacion LIKE ? OR c.telefono LIKE ?
                        GROUP BY c.id ORDER BY c.fecha_registro DESC""", (like,like,like,like))
    else:
        rows = query("""SELECT c.*, c.nombre||' '||c.apellido as nombre_completo, COUNT(e.id) as total_emp, SUM(CASE WHEN e.estado='activo' THEN 1 ELSE 0 END) as activos
                        FROM cliente c LEFT JOIN empenio e ON e.cliente_id=c.id
                        GROUP BY c.id ORDER BY c.fecha_registro DESC""")
    return render_template('clientes.html', clientes=rows, q=q)

@app.route('/clientes/nuevo', methods=['GET','POST'])
def nuevo_cliente():
    if request.method == 'POST':
        cid = execute("INSERT INTO cliente (nombre,apellido,telefono,email,direccion,identificacion,notas) VALUES (?,?,?,?,?,?,?)",
            (request.form['nombre'], request.form['apellido'], request.form.get('telefono'),
             request.form.get('email'), request.form.get('direccion'),
             request.form.get('identificacion') or None, request.form.get('notas')))
        flash('Cliente registrado exitosamente.','success')
        return redirect(url_for('ver_cliente', id=cid))
    return render_template('cliente_form.html', cliente=None)

@app.route('/clientes/<int:id>')
def ver_cliente(id):
    c = query("SELECT c.*, c.nombre||' '||c.apellido as nombre_completo FROM cliente c WHERE c.id=?", (id,), one=True)
    if not c: return "No encontrado", 404
    emps = query("""SELECT e.*, j.descripcion as joya_desc FROM empenio e
                    JOIN joya j ON e.joya_id=j.id WHERE e.cliente_id=? ORDER BY e.id DESC""", (id,))
    return render_template('cliente_detalle.html', cliente=c, empenios=emps)

@app.route('/clientes/<int:id>/editar', methods=['GET','POST'])
def editar_cliente(id):
    c = query("SELECT * FROM cliente WHERE id=?", (id,), one=True)
    if request.method == 'POST':
        execute("UPDATE cliente SET nombre=?,apellido=?,telefono=?,email=?,direccion=?,identificacion=?,notas=? WHERE id=?",
            (request.form['nombre'], request.form['apellido'], request.form.get('telefono'),
             request.form.get('email'), request.form.get('direccion'),
             request.form.get('identificacion') or None, request.form.get('notas'), id))
        flash('Cliente actualizado.','success')
        return redirect(url_for('ver_cliente', id=id))
    return render_template('cliente_form.html', cliente=c)

@app.route('/inventario')
def inventario():
    filtro = request.args.get('estado','todos')
    q = request.args.get('q','')
    sql = "SELECT * FROM joya WHERE 1=1"
    args = []
    if filtro != 'todos': sql += " AND estado=?"; args.append(filtro)
    if q:
        sql += " AND (descripcion LIKE ? OR tipo LIKE ? OR material LIKE ?)"
        like = f'%{q}%'; args += [like,like,like]
    sql += " ORDER BY fecha_ingreso DESC"
    joyas = query(sql, args)
    return render_template('inventario.html', joyas=joyas, filtro=filtro, q=q)

@app.route('/inventario/nueva', methods=['GET','POST'])
def nueva_joya():
    if request.method == 'POST':
        execute("INSERT INTO joya (descripcion,tipo,material,quilates,peso_gramos,valor_estimado,origen,notas) VALUES (?,?,?,?,?,?,?,?)",
            (request.form['descripcion'], request.form.get('tipo'), request.form.get('material'),
             request.form.get('quilates'), request.form.get('peso_gramos') or None,
             request.form.get('valor_estimado') or None, request.form.get('origen','propia'), request.form.get('notas')))
        flash('Joya registrada.','success')
        return redirect(url_for('inventario'))
    return render_template('joya_form.html', joya=None)

@app.route('/inventario/<int:id>/editar', methods=['GET','POST'])
def editar_joya(id):
    joya = query("SELECT * FROM joya WHERE id=?", (id,), one=True)
    if request.method == 'POST':
        execute("UPDATE joya SET descripcion=?,tipo=?,material=?,quilates=?,peso_gramos=?,valor_estimado=?,notas=? WHERE id=?",
            (request.form['descripcion'], request.form.get('tipo'), request.form.get('material'),
             request.form.get('quilates'), request.form.get('peso_gramos') or None,
             request.form.get('valor_estimado') or None, request.form.get('notas'), id))
        flash('Joya actualizada.','success')
        return redirect(url_for('inventario'))
    return render_template('joya_form.html', joya=joya)

@app.route('/empenios')
def empenios():
    filtro = request.args.get('estado','activo')
    hoy = date.today().isoformat()
    sql = """SELECT e.*, c.nombre||' '||c.apellido as cliente_nombre, j.descripcion as joya_desc
             FROM empenio e JOIN cliente c ON e.cliente_id=c.id JOIN joya j ON e.joya_id=j.id"""
    args = []
    if filtro != 'todos': sql += " WHERE e.estado=?"; args.append(filtro)
    sql += " ORDER BY e.id DESC"
    rows = [dict(r) for r in query(sql, args)]
    for e in rows:
        e['interes'] = calcular_interes(e['monto_prestamo'], e['tasa_interes'], e['fecha_inicio'])
        e['pagado'] = total_pagado(e['id'])
        e['saldo'] = round(e['monto_prestamo'] + e['interes'] - e['pagado'], 2)
    return render_template('empenios.html', empenios=rows, filtro=filtro, hoy=hoy)

@app.route('/empenios/nuevo', methods=['GET','POST'])
def nuevo_empenio():
    clientes = query("select c.*, c.nombre||' '||c.apellido as nombre_completo from cliente c group by c.nombre||' '||c.apellido;")
    joyas = query("SELECT * FROM joya WHERE estado='disponible' ORDER BY descripcion")
    if request.method == 'POST':
        fecha_inicio = request.form['fecha_inicio']
        dias_plazo = int(request.form.get('dias_plazo',30))
        fi = datetime.strptime(fecha_inicio,'%Y-%m-%d').date()
        fv = (fi + timedelta(days=dias_plazo)).isoformat()
        joya_id = int(request.form['joya_id'])
        folio = generar_folio()
        eid = execute("INSERT INTO empenio (folio,cliente_id,joya_id,monto_prestamo,tasa_interes,fecha_inicio,fecha_vencimiento,notas) VALUES (?,?,?,?,?,?,?,?)",
            (folio, int(request.form['cliente_id']), joya_id, float(request.form['monto_prestamo']),
             float(request.form.get('tasa_interes',10)), fecha_inicio, fv, request.form.get('notas')))
        execute("UPDATE joya SET estado='empenada', origen='empenada' WHERE id=?", (joya_id,))
        flash(f'Empeño {folio} registrado.','success')
        return redirect(url_for('ver_empenio', id=eid))
    return render_template('empenio_form.html', clientes=clientes, joyas=joyas, hoy=date.today().isoformat())

@app.route('/empenios/<int:id>')
def ver_empenio(id):
    e = query("""SELECT e.*, c.nombre||' '||c.apellido as cliente_nombre, c.telefono as cliente_tel, c.id as cid,
                        j.descripcion as joya_desc, j.tipo as joya_tipo, j.material as joya_material,
                        j.quilates as joya_quilates, j.peso_gramos as joya_peso, j.valor_estimado as joya_valor
                 FROM empenio e JOIN cliente c ON e.cliente_id=c.id JOIN joya j ON e.joya_id=j.id WHERE e.id=?""", (id,), one=True)
    if not e: return "No encontrado", 404
    e = dict(e)
    e['interes'] = calcular_interes(e['monto_prestamo'], e['tasa_interes'], e['fecha_inicio'])
    e['pagado'] = total_pagado(id)
    e['total_pagar'] = round(e['monto_prestamo'] + e['interes'], 2)
    e['saldo'] = round(e['total_pagar'] - e['pagado'], 2)
    hoy = date.today()
    try:
        fv = datetime.strptime(e['fecha_vencimiento'][:10],'%Y-%m-%d').date()
        e['dias_restantes'] = (fv - hoy).days
        e['vencido'] = e['estado'] == 'activo' and fv < hoy
    except:
        e['dias_restantes'] = None; e['vencido'] = False
    pagos = query("SELECT * FROM pago WHERE empenio_id=? ORDER BY fecha DESC", (id,))
    return render_template('empenio_detalle.html', e=e, pagos=pagos, hoy=hoy.isoformat())

@app.route('/empenios/<int:id>/pago', methods=['POST'])
def registrar_pago(id):
    monto = float(request.form['monto'])
    tipo = request.form.get('tipo','interes')
    execute("INSERT INTO pago (empenio_id,monto,tipo,notas) VALUES (?,?,?,?)",
            (id, monto, tipo, request.form.get('notas')))
    if tipo == 'desempenio':
        e = query("SELECT joya_id FROM empenio WHERE id=?", (id,), one=True)
        execute("UPDATE empenio SET estado='desempenado' WHERE id=?", (id,))
        execute("UPDATE joya SET estado='disponible' WHERE id=?", (e['joya_id'],))
        flash('Desempeño registrado. Joya liberada al inventario.','success')
    else:
        flash(f'Pago de ${monto:,.2f} registrado.','success')
    return redirect(url_for('ver_empenio', id=id))

@app.route('/empenios/<int:id>/perder', methods=['POST'])
def perder_empenio(id):
    e = query("SELECT joya_id FROM empenio WHERE id=?", (id,), one=True)
    execute("UPDATE empenio SET estado='perdido' WHERE id=?", (id,))
    execute("UPDATE joya SET estado='disponible', origen='propia' WHERE id=?", (e['joya_id'],))
    flash('Empeño marcado como perdido. La joya pasa al inventario propio.','warning')
    return redirect(url_for('ver_empenio', id=id))

@app.route('/caja')
def caja():
    hoy = date.today()
    mes = int(request.args.get('mes', hoy.month))
    anio = int(request.args.get('anio', hoy.year))
    primer_dia = date(anio, mes, 1).isoformat()
    if mes == 12: ultimo_dia = date(anio+1,1,1) - timedelta(days=1)
    else: ultimo_dia = date(anio,mes+1,1) - timedelta(days=1)
    pagos = query("""SELECT p.*, e.folio, c.nombre||' '||c.apellido as cliente_nombre
                     FROM pago p JOIN empenio e ON p.empenio_id=e.id JOIN cliente c ON e.cliente_id=c.id
                     WHERE p.fecha >= ? AND p.fecha <= ? ORDER BY p.fecha DESC""",
                  (primer_dia, ultimo_dia.isoformat()+' 23:59:59'))
    total_mes = sum(p['monto'] for p in pagos)
    meses = ['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic']
    return render_template('caja.html', pagos=pagos, total_mes=total_mes,
        total_intereses=sum(p['monto'] for p in pagos if p['tipo']=='interes'),
        total_capital=sum(p['monto'] for p in pagos if p['tipo']=='capital'),
        total_desempenios=sum(p['monto'] for p in pagos if p['tipo']=='desempenio'),
        mes=mes, anio=anio, meses=meses)

if __name__ == '__main__':
    init_db()
    app.run(debug=True)
