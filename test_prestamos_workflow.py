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

    def post_loan(self, document, location, exoneracion_categoria=None):
        with self.client.session_transaction() as session:
            session["paciente_validado"] = {
                "identificacion": document, "nombre_completo": "Paciente de prueba",
                "tipo_identificacion": "CC", "cama": location["ubicacion_codigo"],
            }
        control = self.available_control(location["marca_control_requerida"])
        response = self.client.post("/api/prestamos", json={
            "documento": document, "nombre": "Paciente de prueba", "recibe": "Familiar de prueba",
            "parentesco": "Familiar",
            "exoneracion_categoria": exoneracion_categoria or "",
            "habitacion": location["ubicacion_codigo"], "control": control["id"], "confirmar_cama": True, "confirmar_control_fisico": True,
        })
        self.assertEqual(response.status_code, 200, response.get_json())
        return control

    def authorize_payment(self, loan_id):
        response = self.client.post("/api/autorizaciones-salida", json={
            "tipo_autorizacion": "pago", "uso_servicio": True,
        })
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(response.get_json()["prestamo_id"], loan_id)
        return response

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

    def test_dashboard_available_count_subtracts_every_non_available_control(self):
        with sistema.get_local_db_connection() as connection:
            control_ids = [row[0] for row in connection.execute("SELECT id FROM Controles ORDER BY id LIMIT 3").fetchall()]
            connection.execute("UPDATE Controles SET estado='PRESTADO' WHERE id=?", (control_ids[0],))
            connection.execute("UPDATE Controles SET estado='PENDIENTE_DEVOLUCION' WHERE id=?", (control_ids[1],))
            connection.execute("UPDATE Controles SET estado='EN_REVISION' WHERE id=?", (control_ids[2],))

        summary = self.client.get("/api/dashboard/resumen").get_json()
        self.assertEqual(summary["total"], 159)
        self.assertEqual(summary["disponibles"], 156)
        self.assertEqual(summary["no_disponibles"], 3)
        self.assertEqual((summary["en_uso"], summary["pendientes"]), (1, 1))

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
        blocked_return = self.client.post(
            f"/api/prestamos/{loan['id']}/devolucion", json={"recibe": "Paciente de prueba"}
        )
        self.assertEqual(blocked_return.status_code, 409)
        self.assertEqual(self.client.get("/api/dashboard/resumen").get_json()["en_uso"], 1)
        self.authorize_payment(loan["id"])
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

    def test_inventory_and_in_use_apis_return_persisted_active_controls(self):
        location = self.find_location()
        control = self.post_loan("TEST-INVENTORY-API", location)
        inventory = self.client.get("/api/inventario/controles").get_json()["controles"]
        in_use = self.client.get("/api/controles/en-uso").get_json()["controles"]
        item = next(row for row in inventory if row["id"] == control["id"])
        active = next(row for row in in_use if row["documento"] == "TEST-INVENTORY-API")
        self.assertEqual((item["estado"], item["habitacion_actual"]), ("PRESTADO", location["ubicacion_codigo"]))
        self.assertEqual((active["codigo"], active["estado_control"]), (control["codigo"], "PRESTADO"))
        tracking = self.client.get(f"/api/prestamos/{active['prestamo_id']}/historial-traslados")
        self.assertEqual(tracking.status_code, 200, tracking.get_json())
        self.assertEqual(tracking.get_json()["prestamo"]["id"], active["prestamo_id"])
        self.assertEqual(tracking.get_json()["prestamo"]["control_codigo"], control["codigo"])

    def test_exit_approval_is_restricted_to_exempt_active_loans_and_audited(self):
        location = self.find_location()
        self.post_loan("TEST-EXIT-NORMAL", location)
        normal_loan = self.client.get("/api/prestamos").get_json()["prestamos"][0]
        rejected = self.client.post(f"/api/prestamos/{normal_loan['id']}/autorizar-salida")
        self.assertEqual(rejected.status_code, 409)

        exempt_location = self.find_location(location["marca_control_requerida"])
        control = self.post_loan("TEST-EXIT-EXEMPT", exempt_location, "Medicina Prepagada")
        exempt_loan = next(
            loan for loan in self.client.get("/api/prestamos").get_json()["prestamos"]
            if loan["documento"] == "TEST-EXIT-EXEMPT"
        )
        approved = self.client.post(f"/api/prestamos/{exempt_loan['id']}/autorizar-salida")
        self.assertEqual(approved.status_code, 200, approved.get_json())
        self.assertEqual(approved.get_json()["salida_autorizada_por"], "admin")
        with sistema.get_local_db_connection() as connection:
            persisted = connection.execute(
                "SELECT salida_autorizada_at,salida_autorizada_por FROM Prestamos WHERE id=?",
                (exempt_loan["id"],),
            ).fetchone()
            control_state = connection.execute(
                "SELECT estado FROM Controles WHERE id=?", (control["id"],)
            ).fetchone()["estado"]
        self.assertIsNotNone(persisted["salida_autorizada_at"])
        self.assertEqual(persisted["salida_autorizada_por"], "admin")
        self.assertEqual(control_state, "PRESTADO")
        current_loan = self.client.get("/api/historial/prestamo-actual").get_json()["prestamo"]
        self.assertEqual(current_loan["salida_autorizada_por"], "admin")
        self.assertEqual(current_loan["salida_autorizada_at"], approved.get_json()["salida_autorizada_at"])
        repeated = self.client.post(f"/api/prestamos/{exempt_loan['id']}/autorizar-salida")
        self.assertEqual(repeated.status_code, 200)
        self.assertIn("ya había sido autorizada", repeated.get_json()["mensaje"])

    def test_exempt_exit_and_physical_return_update_inventory_and_active_controls(self):
        location = self.find_location()
        control = self.post_loan("TEST-EXIT-RETURN", location, "Medicina Prepagada")
        loan = next(
            item for item in self.client.get("/api/prestamos").get_json()["prestamos"]
            if item["documento"] == "TEST-EXIT-RETURN"
        )
        premature_return = self.client.post(
            f"/api/prestamos/{loan['id']}/devolucion", json={"recibe": "Funcionario"}
        )
        self.assertEqual(premature_return.status_code, 409)
        self.assertEqual(self.client.get("/api/dashboard/resumen").get_json()["en_uso"], 1)

        approval = self.client.post("/api/autorizaciones-salida", json={
            "tipo_autorizacion": "salida_exenta",
            "uso_servicio": True,
            "exoneracion_categoria": "Medicina Prepagada",
        })
        self.assertEqual(approval.status_code, 200, approval.get_json())
        self.assertEqual(approval.get_json()["prestamo_id"], loan["id"])
        returned = self.client.post(
            f"/api/prestamos/{loan['id']}/devolucion", json={"recibe": "Funcionario"}
        )
        self.assertEqual(returned.status_code, 200, returned.get_json())
        inventory = self.client.get("/api/inventario/controles").get_json()["controles"]
        inventory_control = next(item for item in inventory if item["id"] == control["id"])
        in_use = self.client.get("/api/controles/en-uso").get_json()["controles"]
        self.assertEqual(inventory_control["estado"], "DISPONIBLE")
        self.assertIsNone(inventory_control["prestamo_id"])
        available_controls = self.client.get("/api/inventario/controles-disponibles").get_json()["controles"]
        self.assertTrue(any(item["id"] == control["id"] for item in available_controls))
        self.assertFalse(any(item["documento"] == "TEST-EXIT-RETURN" for item in in_use))
        self.assertEqual(self.client.get("/api/dashboard/resumen").get_json()["en_uso"], 0)
        stored_loan = next(
            item for item in self.client.get("/api/prestamos").get_json()["prestamos"]
            if item["documento"] == "TEST-EXIT-RETURN"
        )
        self.assertEqual(stored_loan["estado"], "DEVUELTO")

    def test_no_active_loan_can_receive_audited_exempt_exit_approval(self):
        with self.client.session_transaction() as session:
            session["paciente_validado"] = {
                "identificacion": "TEST-NO-LOAN-EXIT",
                "nombre_completo": "Paciente sin préstamo",
                "cama": "324",
            }
        missing_category = self.client.post("/api/autorizaciones-salida", json={})
        self.assertEqual(missing_category.status_code, 400)

        response = self.client.post("/api/autorizaciones-salida", json={
            "tipo_autorizacion": "salida_exenta",
            "uso_servicio": False,
            "exoneracion_categoria": "Medicina Prepagada",
        })
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(response.get_json()["autorizado_por"], "admin")
        detail = self.client.get("/api/historial/prestamo-actual").get_json()
        self.assertIsNone(detail["prestamo"])
        self.assertEqual(detail["autorizacion_salida"]["exoneracion_categoria"], "Medicina Prepagada")
        self.assertEqual(detail["autorizacion_salida"]["autorizado_por"], "admin")
        self.assertEqual(detail["autorizacion_salida"]["tipo_autorizacion"], "salida_exenta")
        self.assertEqual(detail["autorizacion_salida"]["uso_servicio"], 0)

    def test_payment_authorization_requires_service_and_is_audited(self):
        with self.client.session_transaction() as session:
            session["paciente_validado"] = {
                "identificacion": "TEST-PAYMENT-AUTH",
                "nombre_completo": "Paciente con servicio",
                "cama": "324",
            }
        rejected = self.client.post("/api/autorizaciones-salida", json={
            "tipo_autorizacion": "pago", "uso_servicio": False,
        })
        self.assertEqual(rejected.status_code, 400)
        approved = self.client.post("/api/autorizaciones-salida", json={
            "tipo_autorizacion": "pago", "uso_servicio": True,
        })
        self.assertEqual(approved.status_code, 200, approved.get_json())
        self.assertEqual(approved.get_json()["mensaje"], "Pago autorizado.")
        detail = self.client.get("/api/historial/prestamo-actual").get_json()
        self.assertEqual(detail["autorizacion_salida"]["tipo_autorizacion"], "pago")
        self.assertEqual(detail["autorizacion_salida"]["uso_servicio"], 1)

    def test_location_tracking_api_returns_active_control_and_movement_history(self):
        origin = self.find_location()
        destination = self.find_location(origin["marca_control_requerida"])
        control = self.post_loan("TEST-LOCATION-TRACKING", origin)
        loan = self.client.get("/api/prestamos").get_json()["prestamos"][0]
        transfer = self.client.post(f"/api/prestamos/{loan['id']}/traslado", json={
            "destino": destination["ubicacion_codigo"], "confirmar_control_fisico": True,
        })
        self.assertEqual(transfer.status_code, 200, transfer.get_json())
        compact_destination = destination["ubicacion_codigo"].replace("-", "")
        response = self.client.get("/api/controles/seguimiento?ubicacion=" + compact_destination)
        self.assertEqual(response.status_code, 200, response.get_json())
        item = next(result for result in response.get_json()["seguimientos"] if result["documento"] == "TEST-LOCATION-TRACKING")
        self.assertEqual((item["control"], item["habitacion_actual"]), (control["codigo"], destination["ubicacion_codigo"]))
        self.assertEqual(item["ubicacion_inicial"], origin["ubicacion_codigo"])
        self.assertEqual(item["responsable_entrega"], "admin")
        self.assertEqual(item["confirmacion_fisica_inicial"], 1)
        self.assertEqual(len(item["traslados"]), 1)
        self.assertEqual(item["traslados"][0]["habitacion_origen"], origin["ubicacion_codigo"])
        self.assertEqual(item["traslados"][0]["habitacion_destino"], destination["ubicacion_codigo"])
        by_document = self.client.get("/api/controles/seguimiento?tipo=documento&valor=TEST-LOCATION-TRACKING")
        self.assertEqual(by_document.status_code, 200, by_document.get_json())
        self.assertEqual(by_document.get_json()["seguimientos"][0]["control"], control["codigo"])

    def test_inventory_transfer_requires_physical_confirmation_and_records_timeline(self):
        origin = self.find_location()
        destination = self.find_location(origin["marca_control_requerida"])
        control = self.post_loan("TEST-MODAL-TRANSFER", origin)
        loan = self.client.get("/api/prestamos").get_json()["prestamos"][0]
        payload = {"destino": destination["ubicacion_codigo"], "confirmar_control_fisico": False}
        rejected = self.client.post(f"/api/prestamos/{loan['id']}/traslado", json=payload)
        self.assertEqual(rejected.status_code, 400)
        with sistema.get_local_db_connection() as connection:
            self.assertEqual(connection.execute("SELECT estado FROM Controles WHERE id=?", (control["id"],)).fetchone()[0], "PRESTADO")
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM Traslados WHERE documento='TEST-MODAL-TRANSFER'").fetchone()[0], 0)

        payload["confirmar_control_fisico"] = True
        moved = self.client.post(f"/api/prestamos/{loan['id']}/traslado", json=payload)
        self.assertEqual(moved.status_code, 200, moved.get_json())
        history = self.client.get(f"/api/prestamos/{loan['id']}/historial-traslados").get_json()
        self.assertEqual(history["prestamo"]["fecha_entrega"], loan["fecha_entrega"])
        self.assertEqual(history["prestamo"]["habitacion_inicial"], origin["ubicacion_codigo"])
        self.assertFalse(history["verificar_ubicacion"])
        self.assertEqual(len(history["traslados"]), 1)
        self.assertEqual((history["traslados"][0]["habitacion_origen"], history["traslados"][0]["habitacion_destino"]), (origin["ubicacion_codigo"], destination["ubicacion_codigo"]))
        with sistema.get_local_db_connection() as connection:
            control_state = connection.execute("SELECT estado,ubicacion_asignada FROM Controles WHERE id=?", (control["id"],)).fetchone()
            loan_location = connection.execute("SELECT habitacion_actual,confirmacion_fisica FROM Prestamos WHERE id=?", (loan["id"],)).fetchone()
        self.assertEqual((control_state["estado"], control_state["ubicacion_asignada"]), ("PRESTADO", destination["ubicacion_codigo"]))
        self.assertEqual((loan_location["habitacion_actual"], loan_location["confirmacion_fisica"]), (destination["ubicacion_codigo"], 1))
        self.authorize_payment(loan["id"])
        self.client.post(f"/api/prestamos/{loan['id']}/devolucion", json={"recibe": "Funcionario de prueba"})
        completed_history = self.client.get(f"/api/prestamos/{loan['id']}/historial-traslados").get_json()
        self.assertIsNotNone(completed_history["prestamo"]["fecha_devolucion"])
        self.assertEqual(completed_history["prestamo"]["recibe_devolucion"], "Funcionario de prueba")

    def test_transfer_return_and_new_control_creates_two_periods(self):
        origin = self.find_location()
        destination = self.find_location(origin["marca_control_requerida"])
        old_control = self.post_loan("TEST-002", origin)
        new_control = self.available_control(destination["marca_control_requerida"])
        result = self.client.post("/api/traslados", json={
            "documento": "TEST-002", "origen": origin["ubicacion_codigo"],
            "destino": destination["ubicacion_codigo"], "devolucion_confirmada": True,
            "recibe_control_anterior": "Funcionario de oficina", "parentesco_control_anterior": "Familiar",
            "recibe_nuevo_control": "Paciente de prueba",
            "parentesco_nuevo_control": "Familiar", "nuevo_control": new_control["id"], "confirmar_control_fisico": True,
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
            loan_id = connection.execute("SELECT id FROM Prestamos WHERE documento='TEST-003' AND estado='ACTIVO'").fetchone()[0]
        self.assertEqual(state, "PENDIENTE_DEVOLUCION")
        self.assertEqual(self.client.get("/api/dashboard/resumen").get_json()["pendientes"], 1)
        tracking = self.client.get(f"/api/prestamos/{loan_id}/historial-traslados").get_json()
        self.assertTrue(tracking["verificar_ubicacion"])

    def test_transfer_location_normalizes_compact_bed_alias_without_merging_beds(self):
        self.assertEqual(sistema._canonical_transfer_location("4362"), "436-2")
        self.assertEqual(sistema._canonical_transfer_location("436-2"), "436-2")
        self.assertNotEqual(
            sistema._canonical_transfer_location("436-1"),
            sistema._canonical_transfer_location("436-2"),
        )

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

    def test_transfer_save_uses_same_active_loan_order_as_history(self):
        origin = self.find_location()
        destination = self.find_location(origin["marca_control_requerida"])
        old_control = self.post_loan("TEST-TRANSFER-ORDER", origin)
        new_control = self.available_control(destination["marca_control_requerida"])
        setup = self.client.post("/api/traslados", json={
            "documento": "TEST-TRANSFER-ORDER", "origen": origin["ubicacion_codigo"],
            "destino": destination["ubicacion_codigo"], "novedad_control": "pending",
            "nuevo_control": new_control["id"], "recibe_nuevo_control": "Paciente de prueba",
            "parentesco_nuevo_control": "Familiar",
        })
        self.assertEqual(setup.status_code, 200, setup.get_json())

        with sistema.get_local_db_connection() as connection:
            loans = connection.execute(
                "SELECT id,control_id FROM Prestamos WHERE documento=? AND estado='ACTIVO' ORDER BY id",
                ("TEST-TRANSFER-ORDER",),
            ).fetchall()
            self.assertEqual(len(loans), 2)
            connection.execute(
                "UPDATE Prestamos SET fecha_entrega=?,habitacion_actual=? WHERE id=?",
                ("2026-10-25T10:00:00", origin["ubicacion_codigo"], loans[0]["id"]),
            )
            connection.execute(
                "UPDATE Prestamos SET fecha_entrega=?,habitacion_actual=? WHERE id=?",
                ("2026-10-24T10:00:00", destination["ubicacion_codigo"], loans[1]["id"]),
            )

        history = self.client.get("/api/prestamos").get_json()["prestamos"]
        latest_by_history = next(loan for loan in history if loan["documento"] == "TEST-TRANSFER-ORDER" and loan["estado"] == "ACTIVO")
        self.assertEqual(latest_by_history["habitacion_actual"], origin["ubicacion_codigo"])
        stale_origin = next(
            location["ubicacion_codigo"] for location in sistema.CATALOGO_UBICACIONES.values()
            if location["ubicacion_codigo"] not in {origin["ubicacion_codigo"], destination["ubicacion_codigo"]}
        )
        result = self.client.post("/api/traslados", json={
            "documento": "TEST-TRANSFER-ORDER", "origen": stale_origin,
            "destino": destination["ubicacion_codigo"], "novedad_control": "returned",
            "devolucion_confirmada": True, "recibe_control_anterior": "Funcionario de prueba",
            "parentesco_control_anterior": "Familiar",
        })
        self.assertEqual(result.status_code, 200, result.get_json())
        with sistema.get_local_db_connection() as connection:
            saved_origin = connection.execute(
                "SELECT habitacion_origen FROM Traslados WHERE documento=? ORDER BY id DESC LIMIT 1",
                ("TEST-TRANSFER-ORDER",),
            ).fetchone()[0]
        self.assertEqual(saved_origin, origin["ubicacion_codigo"])

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
        history = self.client.get("/historial")
        self.assertEqual(dashboard.status_code, 200)
        self.assertEqual(transfer.status_code, 200)
        self.assertEqual(history.status_code, 200)
        home_html = dashboard.get_data(as_text=True)
        transfer_html = transfer.get_data(as_text=True)
        history_html = history.get_data(as_text=True)
        self.assertIn('id="history-search-form"', history_html)
        self.assertIn('id="history-search-type"', history_html)
        self.assertIn('Número de Habitación / Cama', history_html)
        self.assertIn('id="history-patient-modal"', history_html)
        self.assertIn('id="history-total"', history_html)
        self.assertIn('id="history-loan-return-form"', history_html)
        self.assertIn('Devolver control', history_html)
        self.assertIn('id="history-authorization-form"', history_html)
        self.assertIn('¿Utilizó el servicio?', history_html)
        self.assertIn('id="history-authorize-payment"', history_html)
        self.assertIn('Autorizar pago', history_html)
        self.assertIn('id="history-authorize-exempt-exit"', history_html)
        self.assertIn('Autorizar salida exenta', history_html)
        self.assertNotIn('history-no-loan-exit-form', history_html)
        self.assertNotIn('Préstamos registrados', history_html)
        self.assertNotIn('id="history-rows"', history_html)
        history_script = self.client.get('/dashboard_modular.js?v=history-fallback-test')
        self.assertIn(b"async function loadCurrentLoanDetail(patient)", history_script.data)
        self.assertIn(b"fetch('/api/prestamos'", history_script.data)
        self.assertIn(b"no respondi\xc3\xb3 en formato JSON", history_script.data)
        self.assertIn(b"response.headers.get('content-type')", history_script.data)
        self.assertIn(b"La sesi\xc3\xb3n expir\xc3\xb3", history_script.data)
        self.assertIn(b"HTTP 405", history_script.data)
        history_script.close()
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
        self.assertNotIn('id="inventory-panel"', home_html)
        self.assertIn('id="inventory-detail-modal"', home_html)
        self.assertIn('id="inventory-page-next"', home_html)
        self.assertIn('id="timeline-page-next"', home_html)
        self.assertIn('id="inventory-back-to-list"', home_html)
        self.assertNotIn('id="location-tracking-form"', home_html)
        self.assertNotIn('id="tracking-control-patient"', home_html)
        self.assertIn('id="tracking-patient-summary"', home_html)
        self.assertIn('id="tracking-patient-name"', home_html)
        self.assertIn('id="tracking-patient-document"', home_html)
        self.assertNotIn('id="tracking-search-type"', home_html)
        self.assertIn('Historial y seguimiento de los controles', home_html)
        self.assertNotIn('Historial de traslado</h3>', home_html)
        self.assertIn('id="export-transfer-pdf"', home_html)
        self.assertNotIn('id="export-transfer-csv"', home_html)
        self.assertNotIn('id="inventory-transfer-form"', home_html)
        self.assertNotIn('Confirmar traslado', home_html)
        self.assertNotIn('Auditoría', home_html)
        self.assertNotIn('<h4>Control / Paciente</h4>', home_html)
        self.assertNotIn('data-inventory-return=', home_html)
        inventory_modal = home_html.split('<dialog class="workflow-modal inventory-detail-modal"', 1)[1].split('</dialog>', 1)[0]
        self.assertIn('<h2 id="inventory-detail-title">Seguimiento de controles en uso</h2>', inventory_modal)
        self.assertNotIn('Estado del inventario', inventory_modal)
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
        self.assertIn(b'/img/pingui_exito.jpg', served_script.data)
        self.assertIn(b'/img/pingui_error.jpg', served_script.data)
        self.assertIn(b'YA EST\xc3\x81 PRESTADO', served_script.data)
        self.assertIn(b'originInput.value = String(location)', served_script.data)
        self.assertIn(b'const location = activeLoanLocation || patientLocation', served_script.data)
        served_script.close()
        self.assertNotIn('loan-required-brand', loan_form)
        self.assertNotIn('C?digo del control disponible', loan_form)
        self.assertEqual(transfer_html.count('id="transfer-destination"'), 1)
        self.assertIn('value="returned"', transfer_html)
        self.assertIn('value="pending"', transfer_html)
        self.assertIn('Registro de traslado de pacientes', transfer_html)
        self.assertIn('Control anterior</legend>', transfer_html)
        self.assertIn('Registro del nuevo control</legend>', transfer_html)
        self.assertIn('id="transfer-old-recipient" placeholder="Nombre de quien devuelve el control"', transfer_html)
        self.assertIn('id="transfer-old-received-by" value="Usuario autenticado" readonly', transfer_html)
        self.assertIn('Persona que recibe el control', transfer_html)
        self.assertIn('id="transfer-new-delivered-by"', transfer_html)
        self.assertNotIn('id="transfer-next-step"', transfer_html)
        self.assertNotIn('id="transfer-previous-step"', transfer_html)
        self.assertLess(transfer_html.index('id="transfer-submit"'), transfer_html.index('Regresar al dashboard'))
        self.assertIn('Padre / Madre', transfer_html)
        self.assertIn('id="transfer-search-type"', transfer_html)
        self.assertIn('value="habitacion"', transfer_html)
        self.assertIn('Informaci&#243;n del traslado', transfer_html)
        self.assertNotIn('Cama real de destino', transfer_html)
        self.assertNotIn('id="transfer-date"', transfer_html)
        self.assertNotIn('Gesti?n de habitaci?n', transfer_html)
        self.assertNotIn('C?digo del nuevo control disponible', transfer_html)

    def test_current_loan_history_detail_returns_calendar_days_and_total(self):
        location = self.find_location()
        self.post_loan("TEST-HISTORY-DETAIL", location)
        response = self.client.get("/api/historial/prestamo-actual")
        self.assertEqual(response.status_code, 200, response.get_json())
        data = response.get_json()
        self.assertEqual(data["paciente"]["documento"], "TEST-HISTORY-DETAIL")
        self.assertEqual(data["paciente"]["ubicacion"], location["ubicacion_codigo"])
        self.assertEqual(data["prestamo"]["estado"], "ACTIVO")
        self.assertTrue(data["prestamo"]["id"])
        self.assertGreaterEqual(data["prestamo"]["dias_servicio"], 1)
        self.assertEqual(data["prestamo"]["total"], data["prestamo"]["dias_servicio"] * sistema.PRECIO_DIARIO)
        self.authorize_payment(data["prestamo"]["id"])
        returned = self.client.post(
            f"/api/prestamos/{data['prestamo']['id']}/devolucion",
            json={"recibe": "Persona de prueba"},
        )
        self.assertEqual(returned.status_code, 200, returned.get_json())

    def test_current_loan_history_detail_requires_validated_patient(self):
        with self.client.session_transaction() as session:
            session.pop("paciente_validado", None)
        response = self.client.get("/api/historial/prestamo-actual")
        self.assertEqual(response.status_code, 403)

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
        self.assertIn("control ya no est\u00e1 disponible", response.get_json()["mensaje"])
        with sistema.get_local_db_connection() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM Prestamos WHERE control_id=? AND estado='ACTIVO'", (control["id"],)).fetchone()[0], 1)

    def test_patient_cannot_receive_a_second_active_loan(self):
        location = self.find_location()
        self.post_loan("TEST-ACTIVE-LOAN", location)
        another_control = self.available_control(location["marca_control_requerida"])
        with self.client.session_transaction() as session:
            session["paciente_validado"] = {
                "identificacion": "TEST-ACTIVE-LOAN", "nombre_completo": "Paciente de prueba",
                "tipo_identificacion": "CC", "cama": location["ubicacion_codigo"],
            }
        response = self.client.post("/api/prestamos", json={
            "documento": "TEST-ACTIVE-LOAN", "nombre": "Paciente de prueba", "recibe": "Familiar",
            "habitacion": location["ubicacion_codigo"], "control": another_control["id"],
            "confirmar_cama": True, "confirmar_control_fisico": True,
        })
        self.assertEqual(response.status_code, 409)
        self.assertIn("pr\u00e9stamo activo", response.get_json()["mensaje"])
        with sistema.get_local_db_connection() as connection:
            self.assertEqual(connection.execute("SELECT estado FROM Controles WHERE id=?", (another_control["id"],)).fetchone()[0], "DISPONIBLE")

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

    def test_billing_room_search_prefers_the_patient_with_an_active_local_loan(self):
        location = self.find_location()
        self.post_loan("TEST-BILLING-ROOM", location)
        response = self.client.get(
            f"/api/paciente/habitacion/{location['ubicacion_codigo']}?contexto=cobro"
        )
        self.assertEqual(response.status_code, 200, response.get_json())
        patients = response.get_json()["pacientes"]
        self.assertEqual(len(patients), 1)
        self.assertEqual(patients[0]["identificacion"], "TEST-BILLING-ROOM")
        self.assertEqual(patients[0]["cama"], location["ubicacion_codigo"])
        self.assertEqual(patients[0]["origen_datos"], "prestamo_local")

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

    def test_room_search_does_not_show_patient_moved_to_another_room(self):
        patient = {
            "identificacion": "TEST-MOVED-ROOM", "nombre_completo": "Paciente trasladado",
            "tipo_identificacion": "CC", "cama": "325-1", "dias_estancia": 2,
        }
        with sistema.get_local_db_connection() as connection:
            connection.execute(
                "INSERT INTO Traslados(documento,habitacion_origen,habitacion_destino,fecha_movimiento) VALUES(?,?,?,?)",
                ("TEST-MOVED-ROOM", "325-1", "308-1", "2026-10-27T09:00:00"),
            )
        with patch.object(sistema, "ORACLE_PASSWORD", "configured"), patch.object(
            sistema, "buscar_por_habitacion", return_value=[patient]
        ):
            response = self.client.get("/api/paciente/habitacion/325")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.get_json()["mensaje"], "No se encontraron pacientes registrados en esa habitación.")
        dashboard = self.client.get("/dashboard").get_data(as_text=True)
        self.assertIn('id="home-bed-query"', dashboard)

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

