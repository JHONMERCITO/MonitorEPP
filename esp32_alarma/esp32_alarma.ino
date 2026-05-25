/**
 * ==============================================================
 *  ACTUADOR ESP32 — Sistema de Monitoreo de EPP
 * ==============================================================
 *  Descripción:
 *    Escucha señales UDP desde la PC con Python/YOLOv8.
 *    Al recibir "ALERT" activa el Buzzer y el LED rojo 3 segundos.
 *    Al recibir "OK"    apaga Buzzer y LED inmediatamente.
 *
 *  Placa recomendada en Arduino IDE:
 *    "ESP32 Dev Module" (Board Manager: esp32 by Espressif)
 *
 *  Librerías requeridas (ya incluidas con el core ESP32):
 *    WiFi.h  /  WiFiUDP.h
 *
 *  Conexiones de pines: ver guia_pines.md
 * ==============================================================
 */

#include <WiFi.h>
#include <WiFiUDP.h>

// ============================================================
//  CONFIGURACIÓN — Modificar antes de compilar
// ============================================================

const char* SSID     = "NombreDetuRed";    // ← Tu red WiFi
const char* PASSWORD = "TuContraseña";     // ← Tu contraseña WiFi

// El ESP32 obtendrá IP por DHCP. Para IP fija ver sección más abajo.
const unsigned int UDP_PORT = 4210;        // Debe coincidir con detector_epp.py

// Pines
const int PIN_LED    = 2;    // LED rojo (GPIO 2 = LED built-in en muchas placas)
const int PIN_BUZZER = 4;    // Buzzer activo o pasivo (GPIO 4)

// Duración de la alarma en milisegundos
const unsigned long DURACION_ALARMA_MS = 3000;

// Frecuencia del buzzer (solo si es PASIVO; ignorada en buzzer activo)
const int FREQ_BUZZER = 2000;   // 2 kHz
const int CANAL_PWM   = 0;
const int RESOL_PWM   = 8;


// ============================================================
//  VARIABLES GLOBALES
// ============================================================

WiFiUDP udp;
char    bufferUDP[64];
bool    alarmaActiva    = false;
unsigned long tiempoInicioAlarma = 0;


// ============================================================
//  FUNCIONES AUXILIARES
// ============================================================

/** Activa Buzzer + LED */
void activarAlarma() {
  if (!alarmaActiva) {
    Serial.println("[ALARMA] *** INFRACCION EPP — Activando alarma ***");
    alarmaActiva         = true;
    tiempoInicioAlarma   = millis();
  }
  // Encender LED
  digitalWrite(PIN_LED, HIGH);
  // Encender Buzzer (PWM para buzzer pasivo)
  ledcWrite(CANAL_PWM, 128);   // 50% duty cycle
}

/** Apaga Buzzer + LED */
void desactivarAlarma() {
  if (alarmaActiva) {
    Serial.println("[ALARMA] Zona segura. Apagando alarma.");
  }
  alarmaActiva = false;
  digitalWrite(PIN_LED, LOW);
  ledcWrite(CANAL_PWM, 0);
}


// ============================================================
//  SETUP
// ============================================================

void setup() {
  Serial.begin(115200);
  Serial.println("\n========================================");
  Serial.println("  ESP32 — Monitor EPP Actuador");
  Serial.println("========================================");

  // --- Configurar pines ---
  pinMode(PIN_LED, OUTPUT);
  digitalWrite(PIN_LED, LOW);

  // Configurar PWM para buzzer
  ledcSetup(CANAL_PWM, FREQ_BUZZER, RESOL_PWM);
  ledcAttachPin(PIN_BUZZER, CANAL_PWM);
  ledcWrite(CANAL_PWM, 0);

  // --- Conectar WiFi ---
  Serial.printf("\nConectando a WiFi: %s", SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(SSID, PASSWORD);

  int intentos = 0;
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
    intentos++;
    if (intentos > 40) {
      Serial.println("\nERROR: No se pudo conectar al WiFi.");
      Serial.println("Verifica SSID y PASSWORD. Reiniciando en 5s...");
      delay(5000);
      ESP.restart();
    }
  }

  Serial.println(" ¡Conectado!");
  Serial.print("  IP del ESP32: ");
  Serial.println(WiFi.localIP());
  Serial.printf("  Escuchando UDP en puerto: %d\n\n", UDP_PORT);

  // --- Iniciar servidor UDP ---
  udp.begin(UDP_PORT);

  // Test rápido de hardware (beep corto al iniciar)
  Serial.println("  [TEST] Beep de inicio...");
  digitalWrite(PIN_LED, HIGH);
  ledcWrite(CANAL_PWM, 128);
  delay(200);
  desactivarAlarma();
  Serial.println("  Sistema listo.\n");
}


// ============================================================
//  LOOP
// ============================================================

void loop() {
  // --- Leer paquetes UDP ---
  int tamPaquete = udp.parsePacket();
  if (tamPaquete > 0) {
    int len = udp.read(bufferUDP, sizeof(bufferUDP) - 1);
    if (len > 0) {
      bufferUDP[len] = '\0';   // Null-terminate
      String mensaje = String(bufferUDP);
      mensaje.trim();

      Serial.printf("[UDP] Recibido: \"%s\" desde %s:%d\n",
                    mensaje.c_str(),
                    udp.remoteIP().toString().c_str(),
                    udp.remotePort());

      if (mensaje == "ALERT") {
        activarAlarma();
        tiempoInicioAlarma = millis();   // Reiniciar temporizador en cada ALERT
      } else if (mensaje == "OK") {
        desactivarAlarma();
      }
    }
  }

  // --- Auto-apagar después de DURACION_ALARMA_MS ---
  if (alarmaActiva) {
    if (millis() - tiempoInicioAlarma >= DURACION_ALARMA_MS) {
      Serial.println("[ALARMA] Tiempo cumplido. Apagando automaticamente.");
      desactivarAlarma();
    }
  }

  // --- Imprimir IP periódicamente (ayuda para configurar detector_epp.py) ---
  static unsigned long ultimoReportIP = 0;
  if (millis() - ultimoReportIP >= 10000) {
    ultimoReportIP = millis();
    Serial.printf("[INFO] IP: %s  |  Puerto UDP: %d  |  Alarma: %s\n",
                  WiFi.localIP().toString().c_str(),
                  UDP_PORT,
                  alarmaActiva ? "ACTIVA" : "inactiva");
  }
}


// ============================================================
//  NOTA: IP FIJA (opcional)
// ============================================================
// Si quieres asignar una IP fija al ESP32, agrega esto ANTES de WiFi.begin():
//
//   IPAddress ip(192, 168, 1, 200);
//   IPAddress gateway(192, 168, 1, 1);
//   IPAddress subnet(255, 255, 255, 0);
//   WiFi.config(ip, gateway, subnet);
//
// Luego usa esa misma IP en detector_epp.py → ESP32_IP = "192.168.1.200"
