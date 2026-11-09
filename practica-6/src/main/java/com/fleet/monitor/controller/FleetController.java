package com.fleet.monitor.controller;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Date;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/fleet")
public class FleetController {

    @GetMapping("/status")
    public ResponseEntity<Map<String, Object>> getStatus() {
        Map<String, Object> status = new LinkedHashMap<>();
        status.put("totalVehicles", 3);
        status.put("activeAlerts", 2);
        status.put("timestamp", new Date());
        return ResponseEntity.ok(status);
    }

    @GetMapping("/vehicle/{id}/telemetria")
    public ResponseEntity<List<String>> getTelemetria(@PathVariable String id) {
        return ResponseEntity.ok(List.of("Datos de telemetria para " + id));
    }

}

/*
 * Pruebas desde la terminal (puerto 8080):
 *
 * curl http://localhost:8080/api/fleet/status
 * curl http://localhost:8080/api/fleet/vehicle/VH-001/telemetria
 */
