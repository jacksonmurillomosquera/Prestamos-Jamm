"""Pruebas de inventario y ciclo de vida del prÃ©stamo usando una SQLite temporal."""
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

import app as sistema


class LoanWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        sistema.LOCAL_DB_PATH = os.path.join(self.temp.name, "test.sqlite3")
        sistema.ensure_local_inventory()
        sistema.sincronizar_prestamos_activos()
        self.client = sistema.app.test_client()
        with self.client.session_transaction() as session:
            session["usuario"] = "admin"
            session["usuario_historia"] = "TEST-HIS-USER"

    def tearDown(self):
        self.temp.cleanup()

    def test_login_form_uses_history_clinic_credentials_route(self):
        client = sistema.app.test_client()
        response = client.get("/")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('action="/login_hc"', html)
        self.assertIn('name="usuario_hc"', html)
        self.assertIn('name="password"', html)
        self.assertIn("Usuario de Historia Clínica", html)

    def test_history_clinic_login_authenticates_without_storing_password(self):
        with patch.object(sistema, "validar_credenciales_historia_clinica", return_value=(True, None)) as validator:
            response = self.client.post("/login_hc", data={"usuario_hc": "HC-007", "password": "secret"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/dashboard")
        validator.assert_called_once_with("HC-007", "secret")
        with self.client.session_transaction() as session:
            self.assertEqual(session["usuario_historia"], "HC-007")
            self.assertNotIn("password", session)

    def test_history_clinic_login_handles_invalid_credentials_and_oracle_outage(self):
        with patch.object(sistema, "validar_credenciales_historia_clinica", return_value=(False, "invalid")):
            invalid = self.client.post("/login_hc", data={"usuario_hc": "HC-007", "password": "bad"})
        self.assertEqual(invalid.status_code, 401)
        self.assertIn("Usuario o contraseña de Historia Clínica incorrectos", invalid.get_data(as_text=True))

        with patch.object(sistema, "validar_credenciales_historia_clinica", side_effect=RuntimeError("network")):
            unavailable = self.client.post("/login_hc", data={"usuario_hc": "HC-007", "password": "secret"})
        self.assertEqual(unavailable.status_code, 503)
        self.assertIn("No fue posible conectar con Historia Clínica", unavailable.get_data(as_text=True))

    def find_location(self, different_from=None):
        return next(
            (location for location in sistema.CATALOGO_UBICACIONES.values()
             if different_from is None or location["marca_control_requerida"] != different_from),
            None,
        )

    def available_control(self, brand):
        with sistema.get_local_db_connection() as connection:
            return connection.execute(
                "SELECT id,codigo FROM Controles WHERE estado='DISPONIBLE' AND marca=? ORDER BY id LIMIT 1",
                (brand,),
            ).fetchone()

    def post_loan(self, document, location):
        with self.client.session_transaction() as session:
            session["paciente_validado"] = {
                "identificacion": document, "nombre_completo": "Paciente de prueba",
                "tipo_identificacion": "CC", "cama": location["ubicacion_codigo"],
            }
        control = self.available_control(location["marca_control_requerida"])
        response = self.client.post("/api/prestamos", json={
            "documento": document, "nombre": "Paciente de prueba", "recibe": "Familiar de prueba",
            "parentesco": "Familiar",
            "habitacion": location["ubicacion_codigo"], "control": control["id"], "confirmar_cama": True, "confirmar_control_fisico": True,
        })
        self.assertEqual(response.status_code, 200, response.get_json())
        return control

    def test_inventory_starts_at_159_and_idempotent(self):
        summary = self.client.get("/api/dashboard/resumen").get_json()
        self.assertEqual((summary["disponibles"], summary["en_uso"], summary["pendientes"]), (159, 0, 0))
        physical = self.client.get("/api/inventario/controles-disponibles").get_json()
        self.assertEqual(len(physical["controles"]), 159)
        self.assertTrue(all(control["estado"] == "DISPONIBLE" for control in physical["controles"]))
        sistema.ensure_local_inventory()
        with sistema.get_local_db_connection() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM Controles").fetchone()[0], 159)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM Prestamos").fetchone()[0], 0)

    def test_room_catalog_is_persisted_and_controls_filter_by_required_brand(self):
        locations = self.client.get("/api/catalogo/ubicaciones").get_json()
        self.assertTrue(locations["persistido"])
        self.assertEqual(len(locations["ubicaciones"]), len(sistema.CATALOGO_UBICACIONES))
        room_307 = next(item for item in locations["ubicaciones"] if item["ubicacion_codigo"] == "307")
        self.assertEqual((room_307["servicio"], room_307["piso"], room_307["marca_control_requerida"]), ("3T3", "3", "PANASONIC"))

        available = self.client.get("/api/catalogo/ubicaciones/307/controles")
        self.assertEqual(available.status_code, 200, available.get_json())
        data = available.get_json()
        self.assertEqual(data["marca_requerida"], "PANASONIC")
        self.assertTrue(data["controles"])
        self.assertTrue(all(control["marca"] == "PANASONIC" for control in data["controles"]))

    def test_loan_rejects_control_with_brand_incompatible_with_room(self):
        room = sistema.CATALOGO_UBICACIONES["307"]
        wrong_control = self.available_control("SONY")
        with self.client.session_transaction() as session:
            session["paciente_validado"] = {
                "identificacion": "TEST-WRONG-BRAND", "nombre_completo": "Paciente de prueba",
                "tipo_identificacion": "CC", "cama": "307",
            }
        response = self.client.post("/api/prestamos", json={
            "documento": "TEST-WRONG-BRAND", "nombre": "Paciente de prueba", "recibe": "Familiar",
            "parentesco": "Familiar", "habitacion": "307", "control": wrong_control["id"],
            "confirmar_cama": True, "confirmar_control_fisico": True,
        })
        self.assertEqual(response.status_code, 409)
        with sistema.get_local_db_connection() as connection:
            state = connection.execute("SELECT estado FROM Controles WHERE id=?", (wrong_control["id"],)).fetchone()[0]
        self.assertEqual(state, "DISPONIBLE")

    def test_started_daily_blocks_round_up(self):
        start = datetime(2026, 10, 9, 6)
        self.assertEqual(sistema.calcular_total(fecha_inicio=start, fecha_fin=start), 3000)
        self.assertEqual(sistema.calcular_total(fecha_inicio=start, fecha_fin=start + timedelta(hours=1)), 3000)
        self.assertEqual(sistema.calcular_total(fecha_inicio=start, fecha_fin=start + timedelta(hours=12)), 3000)
        self.assertEqual(sistema.calcular_total(fecha_inicio=start, fecha_fin=start + timedelta(hours=24)), 3000)
        self.assertEqual(sistema.calcular_total(fecha_inicio=start, fecha_fin=start + timedelta(hours=25)), 6000)
        self.assertEqual(sistema.calcular_total(fecha_inicio=start, fecha_fin=start + timedelta(hours=48)), 6000)
        self.assertEqual(sistema.calcular_total(fecha_inicio=start, fecha_fin=start + timedelta(hours=96)), 12000)

    def test_delivery_return_and_persisted_inventory(self):
        location = self.find_location()
        control = self.post_loan("TEST-001", location)
        summary = self.client.get("/api/dashboard/resumen").get_json()
        self.assertEqual((summary["disponibles"], summary["en_uso"]), (158, 1))
        loan = self.client.get("/api/prestamos").get_json()["prestamos"][0]
        self.assertEqual(loan["parentesco"], "Familiar")
        returned = self.client.post("/api/prestamos/{}/devolucion".format(loan["id"]), json={"recibe": "Paciente de prueba"})
        self.assertEqual(returned.status_code, 200, returned.get_json())
        self.assertGreaterEqual(returned.get_json()["valor_total"], 3000)
        with sistema.get_local_db_connection() as connection:
            state = connection.execute("SELECT estado FROM Controles WHERE id=?", (control["id"],)).fetchone()[0]
            persisted = connection.execute("SELECT estado,fecha_devolucion FROM Prestamos WHERE id=?", (loan["id"],)).fetchone()
        self.assertEqual(state, "DISPONIBLE")
        self.assertEqual(persisted["estado"], "DEVUELTO")
        self.assertIsNotNone(persisted["fecha_devolucion"])
        sistema.ensure_local_inventory()  # application restart is idempotent
        self.assertEqual(self.client.get("/api/dashboard/resumen").get_json()["disponibles"], 159)

    def test_transfer_return_and_new_control_creates_two_periods(self):
        origin = self.find_location()
        destination = self.find_location(origin["marca_control_requerida"])
        old_control = self.post_loan("TEST-002", origin)
        new_control = self.available_control(destination["marca_control_requerida"])
        result = self.client.post("/api/traslados", json={
            "documento": "TEST-002", "origen": origin["ubicacion_codigo"],
            "destino": destination["ubicacion_codigo"], "devolucion_confirmada": True,
            "recibe_control_anterior": "Funcionario de oficina", "recibe_nuevo_control": "Paciente de prueba",
            "nuevo_control": new_control["id"], "confirmar_control_fisico": True,
        })
        self.assertEqual(result.status_code, 200, result.get_json())
        with sistema.get_local_db_connection() as connection:
            old_state = connection.execute("SELECT estado FROM Controles WHERE id=?", (old_control["id"],)).fetchone()[0]
            new_state = connection.execute("SELECT estado FROM Controles WHERE id=?", (new_control["id"],)).fetchone()[0]
            loans = connection.execute("SELECT COUNT(*) FROM Prestamos WHERE documento='TEST-002'").fetchone()[0]
            moves = connection.execute("SELECT COUNT(*) FROM Traslados WHERE documento='TEST-002' AND devolucion_confirmada=1").fetchone()[0]
        self.assertEqual((old_state, new_state, loans, moves), ("DISPONIBLE", "PRESTADO", 2, 1))

    def test_transfer_without_physical_return_stays_pending(self):
        origin = self.find_location()
        destination = self.find_location(origin["marca_control_requerida"])
        control = self.post_loan("TEST-003", origin)
        result = self.client.post("/api/traslados", json={
            "documento": "TEST-003", "origen": origin["ubicacion_codigo"],
            "destino": destination["ubicacion_codigo"], "devolucion_confirmada": False, "novedad_control": "pending",
        })
        self.assertEqual(result.status_code, 200, result.get_json())
        with sistema.get_local_db_connection() as connection:
            state = connection.execute("SELECT estado FROM Controles WHERE id=?", (control["id"],)).fetchone()[0]
        self.assertEqual(state, "PENDIENTE_DEVOLUCION")
        self.assertEqual(self.client.get("/api/dashboard/resumen").get_json()["pendientes"], 1)

    def test_transfer_can_deliver_new_control_while_old_remains_pending(self):
        origin = self.find_location()
        destination = self.find_location(origin["marca_control_requerida"])
        old_control = self.post_loan("TEST-PENDING-NEW", origin)
        new_control = self.available_control(destination["marca_control_requerida"])
        response = self.client.post("/api/traslados", json={
            "documento":"TEST-PENDING-NEW", "origen":origin["ubicacion_codigo"], "destino":destination["ubicacion_codigo"],
            "devolucion_confirmada":False, "nuevo_control":new_control["id"], "recibe_nuevo_control":"Paciente de prueba", "confirmar_control_fisico":True,
        })
        self.assertEqual(response.status_code, 200, response.get_json())
        with sistema.get_local_db_connection() as connection:
            states = connection.execute("SELECT id,estado FROM Controles WHERE id IN (?,?) ORDER BY id", (old_control["id"],new_control["id"])).fetchall()
            active = connection.execute("SELECT COUNT(*) FROM Prestamos WHERE documento='TEST-PENDING-NEW' AND estado='ACTIVO'").fetchone()[0]
        self.assertEqual([row["estado"] for row in states], ["PENDIENTE_DEVOLUCION", "PRESTADO"])
        self.assertEqual(active, 2)

    def test_valid_patient_without_loan_can_transfer_without_new_control(self):
        origin = self.find_location()
        destination = self.find_location(origin["marca_control_requerida"])
        with self.client.session_transaction() as session:
            session["paciente_validado"] = {
                "identificacion": "TEST-005", "nombre_completo": "Paciente sin control",
                "tipo_identificacion": "CC", "cama": origin["ubicacion_codigo"],
            }
        response = self.client.post("/api/traslados", json={
            "documento": "TEST-005", "origen": origin["ubicacion_codigo"],
            "destino": destination["ubicacion_codigo"], "devolucion_confirmada": False, "novedad_control": "no_control",
        })
        self.assertEqual(response.status_code, 200, response.get_json())
        with sistema.get_local_db_connection() as connection:
            loans = connection.execute("SELECT COUNT(*) FROM Prestamos").fetchone()[0]
            movement = connection.execute("SELECT control_id FROM Traslados WHERE documento='TEST-005'").fetchone()
        self.assertEqual(loans, 0)
        self.assertIsNone(movement["control_id"])

    def test_no_control_cannot_be_declared_while_a_loan_is_active(self):
        origin = self.find_location()
        destination = self.find_location(origin["marca_control_requerida"])
        control = self.post_loan("TEST-NO-CONTROL-CONFLICT", origin)
        response = self.client.post("/api/traslados", json={
            "documento": "TEST-NO-CONTROL-CONFLICT", "origen": origin["ubicacion_codigo"],
            "destino": destination["ubicacion_codigo"], "novedad_control": "no_control",
        })
        self.assertEqual(response.status_code, 409)
        with sistema.get_local_db_connection() as connection:
            self.assertEqual(connection.execute("SELECT estado FROM Controles WHERE id=?", (control["id"],)).fetchone()[0], "PRESTADO")
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM Traslados WHERE documento='TEST-NO-CONTROL-CONFLICT'").fetchone()[0], 0)

    def test_physical_return_cannot_be_processed_twice(self):
        origin = self.find_location()
        destination = self.find_location(origin["marca_control_requerida"])
        control = self.post_loan("TEST-DOUBLE-RETURN", origin)
        payload = {
            "documento": "TEST-DOUBLE-RETURN", "origen": origin["ubicacion_codigo"],
            "destino": destination["ubicacion_codigo"], "novedad_control": "returned",
            "devolucion_confirmada": True, "recibe_control_anterior": "Funcionario de prueba",
        }
        first = self.client.post("/api/traslados", json=payload)
        second = self.client.post("/api/traslados", json=payload)
        self.assertEqual(first.status_code, 200, first.get_json())
        self.assertEqual(second.status_code, 409)
        with sistema.get_local_db_connection() as connection:
            self.assertEqual(connection.execute("SELECT estado FROM Controles WHERE id=?", (control["id"],)).fetchone()[0], "DISPONIBLE")
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM Traslados WHERE documento='TEST-DOUBLE-RETURN'").fetchone()[0], 1)

    def test_unvalidated_patient_cannot_get_control(self):
        location = self.find_location()
        control = self.available_control(location["marca_control_requerida"])
        response = self.client.post("/api/prestamos", json={
            "documento": "FAKE", "nombre": "No validado", "recibe": "Alguien",
            "habitacion": location["ubicacion_codigo"], "control": control["id"],
        })
        self.assertEqual(response.status_code, 403)
        with sistema.get_local_db_connection() as connection:
            self.assertEqual(connection.execute("SELECT estado FROM Controles WHERE id=?", (control["id"],)).fetchone()[0], "DISPONIBLE")

    def test_loan_accepts_employee_confirmed_control_without_location_mapping(self):
        location = self.find_location()
        control = self.available_control(location["marca_control_requerida"])
        with self.client.session_transaction() as session:
            session["paciente_validado"] = {"identificacion":"TEST-UNMAPPED", "nombre_completo":"Paciente de prueba", "cama":location["ubicacion_codigo"]}
        response = self.client.post("/api/prestamos", json={"documento":"TEST-UNMAPPED", "nombre":"Paciente de prueba", "recibe":"Familiar", "habitacion":location["ubicacion_codigo"], "control":control["id"], "confirmar_cama":True, "confirmar_control_fisico":True})
        self.assertEqual(response.status_code, 200, response.get_json())
        with sistema.get_local_db_connection() as connection:
            self.assertEqual(connection.execute("SELECT estado FROM Controles WHERE id=?", (control["id"],)).fetchone()[0], "PRESTADO")
            self.assertEqual(connection.execute("SELECT confirmacion_fisica FROM Prestamos").fetchone()[0], 1)

    def test_loan_rejects_a_room_other_than_validated_patient_bed(self):
        current = self.find_location()
        different = next(item for item in sistema.CATALOGO_UBICACIONES.values() if item["ubicacion_codigo"] != current["ubicacion_codigo"])
        control = self.available_control(different["marca_control_requerida"])
        with self.client.session_transaction() as session:
            session["paciente_validado"] = {"identificacion":"TEST-007","nombre_completo":"Paciente de prueba","cama":current["ubicacion_codigo"]}
        response = self.client.post("/api/prestamos", json={
            "documento":"TEST-007","nombre":"Paciente de prueba","recibe":"Familiar",
            "habitacion":different["ubicacion_codigo"],"control":control["id"], "confirmar_cama":True, "confirmar_control_fisico":True,
        })
        self.assertEqual(response.status_code, 409)
        with sistema.get_local_db_connection() as connection:
            self.assertEqual(connection.execute("SELECT estado FROM Controles WHERE id=?",(control["id"],)).fetchone()[0],"DISPONIBLE")

    def test_loan_rejects_a_different_bed_in_the_same_shared_room(self):
        locations = list(sistema.CATALOGO_UBICACIONES.values())
        patient_location = next(item for item in locations if item["ubicacion_codigo"] == "308-1")
        other_bed = next(item for item in locations if item["ubicacion_codigo"] == "308-2")
        control = self.available_control(other_bed["marca_control_requerida"])
        with self.client.session_transaction() as session:
            session["paciente_validado"] = {"identificacion":"TEST-SHARED-BED", "nombre_completo":"Paciente de prueba", "cama":patient_location["ubicacion_codigo"]}
        response = self.client.post("/api/prestamos", json={
            "documento":"TEST-SHARED-BED", "nombre":"Paciente de prueba", "recibe":"Familiar",
            "habitacion":other_bed["ubicacion_codigo"], "control":control["id"], "confirmar_cama":True, "confirmar_control_fisico":True,
        })
        self.assertEqual(response.status_code, 409)
        self.assertIn("no coincide con la cama exacta", response.get_json()["mensaje"])
        with sistema.get_local_db_connection() as connection:
            self.assertEqual(connection.execute("SELECT estado FROM Controles WHERE id=?", (control["id"],)).fetchone()[0], "DISPONIBLE")

    def test_patient_and_transfer_pages_render_simplified_forms(self):
        dashboard = self.client.get("/dashboard")
        transfer = self.client.get("/traslado")
        self.assertEqual(dashboard.status_code, 200)
        self.assertEqual(transfer.status_code, 200)
        home_html = dashboard.get_data(as_text=True)
        transfer_html = transfer.get_data(as_text=True)
        loan_form = home_html.split('<form id="home-loan-form"', 1)[1].split('</form>', 1)[0]
        self.assertIn('id="loan-room-display"', loan_form)
        self.assertIn('id="loan-bed-display"', loan_form)
        self.assertIn('id="loan-confirm-bed"', loan_form)
        self.assertIn('id="loan-confirm-control"', loan_form)
        self.assertNotIn('id="loan-choice"', home_html)
        self.assertIn('id="result-patient-identity"', home_html)
        self.assertNotIn('id="loan-identity-number"', home_html)
        self.assertNotIn('<dialog class="workflow-modal" id="patient-modal"', home_html)
        self.assertNotIn('Consulta de paciente', home_html)
        self.assertIn('id="room-patient-modal"', home_html)
        self.assertNotIn('Prestar control', home_html)
        self.assertNotIn('Entrega de control', home_html)
        self.assertNotIn('Cancelar selecciÃ³n', home_html)
        self.assertIn('No se cobra servicio de TV a:', home_html)
        self.assertNotIn('Selecciona el paciente y la cama correctos para continuar', home_html)
        self.assertNotIn('quick-action-excess', home_html)
        self.assertIn('dashboard_modular.js?v=loan-actions-20261019', home_html)
        self.assertNotIn('historia-clinica-auth', home_html)
        served_script = self.client.get('/dashboard_modular.js?v=hc-login-20261016')
        self.assertEqual(served_script.status_code, 200)
        self.assertIn(b'const patientWorkflow', served_script.data)
        self.assertIn(b'.showModal()', served_script.data)
        served_script.close()
        self.assertNotIn('loan-required-brand', loan_form)
        self.assertNotIn('C?digo del control disponible', loan_form)
        self.assertEqual(transfer_html.count('id="transfer-destination"'), 1)
        self.assertIn('value="returned"', transfer_html)
        self.assertIn('value="pending"', transfer_html)
        self.assertIn('value="no_control"', transfer_html)
        self.assertIn('id="transfer-confirm-new"', transfer_html)
        self.assertIn('id="transfer-search-type"', transfer_html)
        self.assertIn('value="habitacion"', transfer_html)
        self.assertIn('Informaci&#243;n de traslado', transfer_html)
        self.assertNotIn('Cama real de destino', transfer_html)
        self.assertNotIn('id="transfer-date"', transfer_html)
        self.assertNotIn('Gesti?n de habitaci?n', transfer_html)
        self.assertNotIn('C?digo del nuevo control disponible', transfer_html)

    def test_same_control_cannot_be_loaned_to_two_patients(self):
        location = self.find_location()
        control = self.post_loan("TEST-CONTROL-OWNER", location)
        with self.client.session_transaction() as session:
            session["paciente_validado"] = {"identificacion": "TEST-SECOND-PATIENT", "nombre_completo": "Paciente", "cama": location["ubicacion_codigo"]}
        response = self.client.post("/api/prestamos", json={
            "documento": "TEST-SECOND-PATIENT", "nombre": "Paciente", "recibe": "Familiar",
            "habitacion": location["ubicacion_codigo"], "control": control["id"],
            "confirmar_cama": True, "confirmar_control_fisico": True,
        })
        self.assertEqual(response.status_code, 409)
        with sistema.get_local_db_connection() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM Prestamos WHERE control_id=? AND estado='ACTIVO'", (control["id"],)).fetchone()[0], 1)

    def test_room_search_returns_all_patients_without_selecting_one(self):
        patients = [
            {"tipo_identificacion":"CC", "identificacion":"100", "nombre_completo":"Paciente Uno", "cama":"310-1"},
            {"tipo_identificacion":"TI", "identificacion":"200", "nombre_completo":"Paciente Dos", "cama":"310-2"},
        ]
        with patch.object(sistema, "ORACLE_PASSWORD", "configured"), patch.object(sistema, "buscar_por_habitacion", return_value=patients):
            response = self.client.get("/api/paciente/habitacion/310")
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual([p["cama"] for p in response.get_json()["pacientes"]], ["310-1", "310-2"])
        with self.client.session_transaction() as session:
            self.assertNotIn("paciente_validado", session)

    def test_oracle_search_requires_historia_clinica_user_before_query(self):
        with self.client.session_transaction() as session:
            session.pop("usuario_historia", None)
        with patch.object(sistema, "buscar_por_habitacion") as lookup:
            response = self.client.get("/api/paciente/habitacion/310")
        self.assertEqual(response.status_code, 428)
        self.assertEqual(response.get_json()["mensaje"], sistema.ORACLE_AUTH_MESSAGE)
        lookup.assert_not_called()

    def test_room_search_reports_database_failure_as_server_error(self):
        with patch.object(sistema, "ORACLE_PASSWORD", "configured"), \
                patch.object(sistema, "buscar_por_habitacion", side_effect=RuntimeError("oracle unavailable")):
            response = self.client.get("/api/paciente/habitacion/310")
        self.assertEqual(response.status_code, 500)
        self.assertNotIn("No se encontraron pacientes", response.get_json()["mensaje"])

    def test_room_search_handles_one_three_and_zero_patients(self):
        for count in (1, 3):
            patients = [
                {"tipo_identificacion": "CC", "identificacion": str(100 + i),
                 "nombre_completo": f"Paciente {i}", "cama": f"310-{i + 1}"}
                for i in range(count)
            ]
            with self.subTest(count=count), patch.object(sistema, "ORACLE_PASSWORD", "configured"), \
                    patch.object(sistema, "buscar_por_habitacion", return_value=patients):
                response = self.client.get("/api/paciente/habitacion/310")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(len(response.get_json()["pacientes"]), count)

        with patch.object(sistema, "ORACLE_PASSWORD", "configured"), \
                patch.object(sistema, "buscar_por_habitacion", return_value=[]):
            response = self.client.get("/api/paciente/habitacion/999")
        self.assertEqual(response.status_code, 404)
        self.assertIn("No se encontraron pacientes", response.get_json()["mensaje"])

    def test_bed_formatted_room_searches_base_room_and_rejects_invalid_input(self):
        patients = [{"tipo_identificacion": "CC", "identificacion": "101",
                     "nombre_completo": "Paciente", "cama": "310-1"}]
        with patch.object(sistema, "ORACLE_PASSWORD", "configured"), \
                patch.object(sistema, "buscar_por_habitacion", return_value=patients) as lookup:
            response = self.client.get("/api/paciente/habitacion/310-1")
        self.assertEqual(response.status_code, 200)
        lookup.assert_called_once_with("310", "TEST-HIS-USER")

        response = self.client.get("/api/paciente/habitacion/310%20OR%201%3D1")
        self.assertEqual(response.status_code, 400)

    def test_exact_bed_search_does_not_treat_room_only_census_as_exact_bed(self):
        patient_rows = [{"tipo_identificacion":"CC", "identificacion":"101", "nombre_completo":"Paciente", "cama":"310"}]
        with patch.object(sistema, "ORACLE_PASSWORD", "configured"), patch.object(sistema, "buscar_por_habitacion", return_value=patient_rows):
            response = self.client.get("/api/paciente/habitacion/310-1")
        self.assertEqual(response.status_code, 409)
        self.assertIn("no identifica la cama individual", response.get_json()["mensaje"])


    def test_patient_search_by_identification_and_bed_validates_session(self):
        patient = {"identificacion": "TEST-006", "nombre_completo": "Paciente de prueba", "tipo_identificacion": "CC", "cama": "308-1"}
        with patch.object(sistema, "ORACLE_PASSWORD", "configured"), patch.object(sistema, "buscar_por_identificacion", return_value=patient):
            response = self.client.get("/api/paciente/identificacion/TEST-006")
        self.assertEqual(response.status_code, 200)
        with self.client.session_transaction() as session:
            self.assertEqual(session["paciente_validado"]["identificacion"], "TEST-006")
        with patch.object(sistema, "ORACLE_PASSWORD", "configured"), patch.object(sistema, "buscar_por_cama", return_value=patient):
            response = self.client.get("/api/paciente/cama/308-1")
        self.assertEqual(response.status_code, 200)

    def test_failed_transfer_does_not_release_old_control(self):
        origin = self.find_location()
        destination = self.find_location(origin["marca_control_requerida"])
        old = self.post_loan("TEST-004", origin)
        wrong_control = self.available_control(origin["marca_control_requerida"])
        with sistema.get_local_db_connection() as connection:
            connection.execute("UPDATE Controles SET estado='PRESTADO' WHERE id=?", (wrong_control["id"],))
        response = self.client.post("/api/traslados", json={
            "documento": "TEST-004", "origen": origin["ubicacion_codigo"],
            "destino": destination["ubicacion_codigo"], "devolucion_confirmada": True,
            "recibe_control_anterior": "Funcionario de prueba",
            "recibe_nuevo_control": "Paciente de prueba", "nuevo_control": wrong_control["id"], "confirmar_control_fisico": True,
        })
        self.assertEqual(response.status_code, 409)
        with sistema.get_local_db_connection() as connection:
            old_state = connection.execute("SELECT estado FROM Controles WHERE id=?", (old["id"],)).fetchone()[0]
            loan_state = connection.execute("SELECT estado FROM Prestamos WHERE documento='TEST-004'").fetchone()[0]
        self.assertEqual((old_state, loan_state), ("PRESTADO", "ACTIVO"))


if __name__ == "__main__":
    unittest.main()

