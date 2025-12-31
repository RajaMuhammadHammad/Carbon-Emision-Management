from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_file
from calroutes import cal_bp
import pyodbc
from datetime import datetime
import uuid
import requests
from io import BytesIO
import os
import logging
import traceback
from db import get_db_connection
import google.generativeai as genai

# Configure logging
logging.basicConfig(level=logging.INFO)





# Configure GenAI from env var (do NOT hardcode key)
GENAI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GENAI_API_KEY:
    logging.warning("GENAI_API_KEY not set - Gemini calls will fail until set.")
else:
    genai.configure(api_key=GENAI_API_KEY)


app = Flask(__name__)
app.secret_key = '365D471543655'  # Required for session
 

app.register_blueprint(cal_bp)






# ----------------------
# Routes
# ----------------------
@app.route('/', methods=['GET', 'POST'])
def home():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        try:
            conn = get_db_connection()
            cursor = conn.cursor()
        except Exception:
            logging.error("DB unavailable during login:\n" + traceback.format_exc())
            return render_template('index.html', error="Database unavailable. Please try again in 1-2 minutes.")

        try:    
            cursor.execute("""
                SELECT u.id, u.name, u.email, u.company_id, c.name AS company_name
                FROM Users u
                JOIN Companies c ON u.company_id = c.id
                WHERE u.email = ? AND u.password = ?
            """, (email, password))

            user = cursor.fetchone()

            if not user:
                return render_template('index.html', error="Invalid email or password.")

            user_id = user[0]

            cursor.execute("""
                SELECT TOP 1 access_end
                FROM AccessRoles
                WHERE user_id = ?
                ORDER BY access_end DESC
            """, (user_id,))
            role = cursor.fetchone()

            if role and role.access_end < datetime.now():
                return render_template('index.html', error="Your plan has expired. Please contact Ed-Watch to renew your access.")

            session['user_id'] = user[0]
            session['user_name'] = user[1]
            session['email'] = user[2]
            session['company_id'] = user[3]
            session['company_name'] = user[4]

            session_id = str(uuid.uuid4())
            ip_address = request.remote_addr
            cursor.execute("""
                INSERT INTO UserLogins (user_id, ip_address, session_id)
                VALUES (?, ?, ?)
            """, (user[0], ip_address, session_id))

            conn.commit()
            return redirect(url_for('welcome'))

        finally:
            try:
                cursor.close()
                conn.close()
            except Exception:
                pass

    return render_template('index.html')


@app.route('/logout', methods=['POST'])
def logout():
    session.clear()  # Clear the session
    return jsonify({'success': True}), 200

@app.route('/change-password', methods=['POST'])
def change_password():
    if 'user_id' not in session:
        return jsonify({'message': 'Unauthorized'}), 401

    data = request.get_json()
    current_password = data.get('current_password')
    new_password = data.get('new_password')
    user_id = session['user_id']

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("EXEC ChangeUserPassword ?, ?, ?", (user_id, current_password, new_password))
        conn.commit()
        cursor.close()
        conn.close()

        if cursor.rowcount > 0:
            return jsonify({'message': 'Password changed successfully!'}), 200
        else:
            return jsonify({'message': 'Current password is incorrect or no change made.'}), 400

    except Exception as e:
        print("Password change error:", e)
        return jsonify({'message': str(e) or 'An error occurred. Please try again.'}), 500


@app.route('/welcome')
def welcome():
    if 'user_name' not in session:
        return redirect(url_for('home'))

    company_id = session.get('company_id')


    conn = get_db_connection()
    cursor = conn.cursor()
    # Fetch most recent EdSenseAI record for this company
    cursor.execute("""
        SELECT TOP 1 *
        FROM EdSenseAI
        WHERE company_id = ?
        ORDER BY id DESC
    """, (company_id,))
    row = cursor.fetchone()
    data = dict(zip([column[0] for column in cursor.description], row)) if row else None

    # Fetch company details
    cursor.execute("SELECT * FROM Companies WHERE id = ?", (company_id,))
    company_row = cursor.fetchone()
    company = dict(zip([column[0] for column in cursor.description], company_row)) if company_row else {}

    # Fetch users of this company along with their roles
    cursor.execute("""
        SELECT u.id, u.name, u.email, u.designation,
               ar.role_name, ar.access_start, ar.access_end
        FROM Users u
        LEFT JOIN AccessRoles ar ON u.id = ar.user_id
        WHERE u.company_id = ?
        ORDER BY u.name
    """, (company_id,))
    users = [dict(zip([column[0] for column in cursor.description], u)) for u in cursor.fetchall()]
    
    conn.commit()

    cursor.close()
    conn.close()
    return render_template(
        "welcome.html",
        user_name=session['user_name'],
        email=session.get('email'),
        company_name=session.get('company_name'),
        data=data,
        company=company,
        users=users
    )


@app.route('/edit_company', methods=['POST'])
def edit_company():
    if 'company_id' not in session:
        return redirect(url_for('home'))

    company_id = session['company_id']
    name = request.form.get('name')
    region = request.form.get('region')
    countries = request.form.get('countries')
    sector = request.form.get('sector')
    company_size = request.form.get('company_size')
    listing_status = request.form.get('listing_status')


    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        EXEC sp_UpdateCompany ?, ?, ?, ?, ?, ?, ?
    """, (company_id, name, region, countries, sector, company_size, listing_status))
    conn.commit()
    cursor.close()
    conn.close()

    return redirect(url_for('welcome'))



@app.route('/edit_user_role', methods=['POST'])
def edit_user_role():
    user_id = request.form.get('user_id')
    role_name = request.form.get('role_name')
    access_start = request.form.get('access_start')
    access_end = request.form.get('access_end')

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        EXEC sp_UpdateUserRole ?, ?, ?, ?
    """, (user_id, role_name, access_start, access_end))
    conn.commit()
    cursor.close()
    conn.close()

    return redirect(url_for('welcome'))

from flask import jsonify, send_file
import io



@app.route("/api/carbon/dashboard")
def carbon_dashboard():

    n = int(request.args.get("n", 12))
    KG_TO_TONNE = 1000.0

    if "company_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    company_id = session["company_id"]

    conn = get_db_connection()
    cursor = conn.cursor()

    # Latest emission summary for this company only
    cursor.execute("""
        SELECT TOP 1
            scope1_total,
            scope2_total,
            scope3_total,
            overall_total,
            revenue,
            employees,
            created_at
        FROM CarbonEmission
        WHERE company_id = ?
        ORDER BY created_at DESC
    """, company_id)

    row = cursor.fetchone()
    if not row:
        cursor.close()
        conn.close()
        return jsonify({"error": "No carbon data found for this company"}), 404

    scope1_t = float(row.scope1_total or 0) / KG_TO_TONNE
    scope2_t = float(row.scope2_total or 0) / KG_TO_TONNE
    scope3_t = float(row.scope3_total or 0) / KG_TO_TONNE
    overall_t = float(row.overall_total or 0) / KG_TO_TONNE
    revenue = float(row.revenue or 0)
    employees = float(row.employees or 0)

    intensity_current = overall_t / revenue if revenue > 0 else 0

    # Fetch emission details only for this company
    cursor.execute("""
        SELECT d.scope, d.category, d.item, d.qty, d.unit, d.factor, d.emission,
               FORMAT(d.created_at, 'yyyy-MM-dd') AS created_at
        FROM CarbonEmissionDetails d
        JOIN CarbonEmission e ON d.emission_id = e.id
        WHERE e.company_id = ?
        ORDER BY d.scope, d.category, d.created_at
    """, company_id)

    details = []
    total_em = 0
    primary_em = 0

    for r in cursor.fetchall():
        em = float(r.emission)
        total_em += em
        if r.qty:
            primary_em += em
        details.append({
            "scope": r.scope,
            "category": r.category,
            "item": r.item,
            "qty": float(r.qty) if r.qty else None,
            "unit": r.unit,
            "factor": float(r.factor) if r.factor else None,
            "emission": em,
            "created_at": r.created_at
        })

    primary_pct = (primary_em / total_em * 100) if total_em > 0 else 0

    response = {
        "waterfall": {
            "labels": ["Scope 1", "Scope 2", "Scope 3", "Total"],
            "values": [scope1_t, scope2_t, scope3_t, overall_t],
            "unit": "tCO₂e"
        },
        "intensity": {
            "current": round(intensity_current, 2),
            "unit": "tCO₂e / revenue",
            "series": {"labels": [], "values": []}
        },
        "quality": {
            "primary_proxy_pct": round(primary_pct, 2),
            "note": "Calculated using activity-based records"
        },
        "details": details
    }

    cursor.close()
    conn.close()
    return jsonify(response)


@app.route('/save-company-metrics', methods=['POST'])
def save_company_metrics():
    try:
        data = request.json
        company_id = session.get('company_id')  # ensure company is logged in

        if not company_id:
            return jsonify({"message": "Unauthorized"}), 401

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO CompanyMetrics (
                company_id,
                abatement_capex,
                abatement_opex_npv,
                lifetime_tco2e_avoided,
                roadmap_total_initiatives,
                roadmap_funded_ontrack,
                abatement_cumulative_by_target,
                required_reduction_target,
                scope1_emissions,
                scope2_emissions,
                sector_driver_value,
                scope3_primary_activity,
                scope3_total_activity,
                emission_factor_age_months,
                mwh_total,
                mwh_ppa_rec
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        company_id,
        data.get('abatement_capex'),
        data.get('abatement_opex_npv'),
        data.get('lifetime_tco2e_avoided'),
        data.get('roadmap_total_initiatives'),
        data.get('roadmap_funded_ontrack'),
        data.get('abatement_cumulative_by_target'),
        data.get('required_reduction_target'),
        data.get('scope1_emissions'),
        data.get('scope2_emissions'),
        data.get('sector_driver_value'),
        data.get('scope3_primary_activity'),
        data.get('scope3_total_activity'),
        data.get('emission_factor_age_months'),
        data.get('mwh_total'),
        data.get('mwh_ppa_rec')
        )

        conn.commit()
        conn.close()

        return jsonify({"message": "Company metrics saved successfully"})

    except Exception as e:
        return jsonify({"message": str(e)}), 500

@app.route('/get-latest-company-metrics', methods=['GET'])
def get_latest_company_metrics():
    try:
        company_id = session.get('company_id')

        if not company_id:
            return jsonify(None)

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT TOP 1 *
            FROM CompanyMetrics
            WHERE company_id = ?
            ORDER BY created_at DESC
        """, company_id)

        row = cursor.fetchone()
        conn.close()

        if not row:
            return jsonify(None)

        columns = [column[0] for column in cursor.description]
        data = dict(zip(columns, row))

        return jsonify(data)

    except Exception as e:
        return jsonify({"error": str(e)}), 500



@app.route('/api/benchmark/renewable-electricity')
def benchmark_renewable_electricity():
    if 'company_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    company_id = session['company_id']
    
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Get company's renewable percentage
        cursor.execute("""
    SELECT TOP 1
        mwh_total,
        mwh_ppa_rec,
        CASE 
            WHEN mwh_total > 0 THEN (mwh_ppa_rec * 100.0 / mwh_total)
            ELSE 0 
        END AS company_renewable_pct
    FROM CompanyMetrics
    WHERE company_id = ?
    ORDER BY created_at DESC
""", (company_id,))

        
        company_row = cursor.fetchone()
        
        if not company_row:
            return jsonify({'error': 'No company metrics found. Please add your data first.'}), 404
        
        company_renewable_pct = float(company_row.company_renewable_pct or 0)
        
        # Get company's region
        cursor.execute("SELECT region FROM Companies WHERE id = ?", (company_id,))
        region_row = cursor.fetchone()
        region = region_row.region if region_row else None
        
        # Get benchmark data from RenewableBenchmark
        cursor.execute("""
            WITH RenewableData AS (
                SELECT 
                    country_name,
                    benchmark_year,
                    SUM(CASE WHEN renewable_category = 1 THEN generation_twh ELSE 0 END) AS renewable_twh,
                    SUM(generation_twh) AS total_twh
                FROM RenewableBenchmark
                WHERE benchmark_year = (SELECT MAX(benchmark_year) FROM RenewableBenchmark)
                GROUP BY country_name, benchmark_year
            )
            SELECT 
                country_name,
                benchmark_year,
                CASE 
                    WHEN total_twh > 0 THEN (renewable_twh * 100.0 / total_twh)
                    ELSE 0 
                END AS renewable_pct
            FROM RenewableData
            WHERE country_name = ?
            OR country_name LIKE '%' + ? + '%'
            ORDER BY renewable_pct DESC
        """, (region, region))
        
        benchmark_rows = cursor.fetchall()
        
        # Calculate regional average
        regional_avg = 0
        if benchmark_rows:
            regional_avg = sum(float(row.renewable_pct) for row in benchmark_rows) / len(benchmark_rows)
        
        # Get global leaders (top 10%)
        cursor.execute("""
            WITH RenewableData AS (
                SELECT 
                    country_name,
                    SUM(CASE WHEN renewable_category = 1 THEN generation_twh ELSE 0 END) AS renewable_twh,
                    SUM(generation_twh) AS total_twh
                FROM RenewableBenchmark
                WHERE benchmark_year = (SELECT MAX(benchmark_year) FROM RenewableBenchmark)
                GROUP BY country_name
            )
            SELECT 
                PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY (renewable_twh * 100.0 / NULLIF(total_twh, 0))) OVER() AS leader_threshold
            FROM RenewableData
        """)
        
        leader_row = cursor.fetchone()
        leader_threshold = float(leader_row.leader_threshold) if leader_row else 60
        
        # Determine company status
        status = "Lagging"
        status_color = "#EF4444"  # Red
        
        if company_renewable_pct >= leader_threshold:
            status = "Leader"
            status_color = "#10B981"  # Green
        elif company_renewable_pct >= 40:
            status = "Transitional"
            status_color = "#F59E0B"  # Yellow
        
        response = {
            "company": {
                "renewable_pct": round(company_renewable_pct, 2),
                "status": status,
                "status_color": status_color
            },
            "benchmarks": {
                "regional_avg": round(regional_avg, 2),
                "global_leaders": round(leader_threshold, 2)
            },
            "chart_data": {
                "labels": ["Your Company", "Regional Average", "Global Leaders (Top 10%)"],
                "values": [
                    round(company_renewable_pct, 2),
                    round(regional_avg, 2),
                    round(leader_threshold, 2)
                ],
                "colors": [status_color, "#3B82F6", "#10B981"]
            }
        }
        
        return jsonify(response), 200
        
    except Exception as e:
        logging.error(f"Benchmark error: {e}")
        logging.error(traceback.format_exc())
        return jsonify({'error': 'Failed to calculate benchmark'}), 500

# Run Flask
# ----------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)