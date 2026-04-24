// DEFINICIONES INICIALES
const int CANTIDAD_SENIALES = 2;
const int PINS[CANTIDAD_SENIALES] = {2, 3};
const char* ETIQUETAS[CANTIDAD_SENIALES] = {"555", "FlipFlop"};

// MEDICION DE FRECUENCIA Y PERIODO
int prevState[CANTIDAD_SENIALES] = {LOW, LOW};
unsigned long lastEdgeTime[CANTIDAD_SENIALES] = {0, 0};
unsigned long period_us[CANTIDAD_SENIALES] = {0, 0};
int risingEdges[CANTIDAD_SENIALES] = {0, 0};
float freq_hz[CANTIDAD_SENIALES] = {0, 0};

// DUTY CYCLE
unsigned long lastChangeTime[CANTIDAD_SENIALES] = {0, 0};
unsigned long high_us[CANTIDAD_SENIALES] = {0, 0};
unsigned long low_us[CANTIDAD_SENIALES] = {0, 0};
float duty_percent[CANTIDAD_SENIALES] = {0, 0};

// GRAFICA INICIAL
const unsigned long DURACION_GRAFICA = 10000;  // 10 seg
unsigned long startTime;
bool primeraFase = true;
unsigned long prevSampleTime = 0;
const int SAMPLE_MS = 50;  // <--- MÁS LENTO: antes 10ms, ahora 50ms

// CONTROL DE VELOCIDAD DEL LOOP (sin delay)
unsigned long ultimoLoopTime = 0;
const unsigned long INTERVALO_LOOP_MS = 5;  // pausa no bloqueante de 5ms

void setup() {
  Serial.begin(115200);
  for (int idx = 0; idx < CANTIDAD_SENIALES; idx++) {
    pinMode(PINS[idx], INPUT);
    lastChangeTime[idx] = micros();
  }
  startTime = millis();
  prevSampleTime = millis();
  primeraFase = true;
  ultimoLoopTime = millis();
}

void loop() {
  unsigned long ahoraLoop = millis();
  if (ahoraLoop - ultimoLoopTime < INTERVALO_LOOP_MS) {
    return;  // pausa no bloqueante: sale rápido si no toca
  }
  ultimoLoopTime = ahoraLoop;

  if (primeraFase) {
    faseGraficar();
  } else {
    for (int idx = 0; idx < CANTIDAD_SENIALES; idx++) {
      analizarSenial(idx);
    }
  }
}

// ===================== GRAFICAR =====================
void faseGraficar() {
  unsigned long ahora = millis();
  if (ahora - startTime >= DURACION_GRAFICA) {
    primeraFase = false;
    return;
  }
  tomarMuestraSiCorresponde();
}

void tomarMuestraSiCorresponde() {
  unsigned long ahora = millis();
  if (ahora - prevSampleTime >= SAMPLE_MS) {
    prevSampleTime = ahora;
    mandarAlPlotter();
  }
}

void mandarAlPlotter() {
  int val555 = digitalRead(PINS[0]);
  int valFF = digitalRead(PINS[1]);

  int nivel555 = transformar(val555, 0);
  int nivelFF = transformar(valFF, 1);

  Serial.print(nivel555);
  Serial.print(",");
  Serial.println(nivelFF);
}

int transformar(int lectura, int cual) {
  if (cual == 0) return (lectura == HIGH) ? 3 : 0;
  return (lectura == HIGH) ? 8 : 5;
}

// ===================== MEDICIONES =====================
void analizarSenial(int idx) {
  int estado = digitalRead(PINS[idx]);
  unsigned long tActual = micros();

  calcularDuty(idx, estado, tActual);

  if (estado == HIGH && prevState[idx] == LOW) {
    manejarFlancoSubida(idx, tActual);
  }

  prevState[idx] = estado;
}

void manejarFlancoSubida(int idx, unsigned long tActual) {
  risingEdges[idx]++;

  bool esElPrimero = (lastEdgeTime[idx] == 0);

  if (!esElPrimero) {
    period_us[idx] = tActual - lastEdgeTime[idx];
    freq_hz[idx] = (period_us[idx] == 0) ? 0 : 1000000.0 / period_us[idx];
  }

  imprimirResultado(idx, esElPrimero);
  lastEdgeTime[idx] = tActual;
}

void calcularDuty(int idx, int estadoActual, unsigned long tActual) {
  if (estadoActual != prevState[idx]) {
    if (estadoActual == HIGH) {
      low_us[idx] = tActual - lastChangeTime[idx];
    } else {
      high_us[idx] = tActual - lastChangeTime[idx];
    }

    if (high_us[idx] > 0 && low_us[idx] > 0) {
      unsigned long sum = high_us[idx] + low_us[idx];
      duty_percent[idx] = (sum == 0) ? 0 : (high_us[idx] * 100.0) / sum;
    }

    lastChangeTime[idx] = tActual;
  }
}

void imprimirResultado(int idx, bool esPrimerFlanco) {
  Serial.print("[");
  Serial.print(ETIQUETAS[idx]);
  Serial.print("] Flanco #");
  Serial.print(risingEdges[idx]);

  if (esPrimerFlanco) {
    Serial.println(" | PRIMER FLANCO");
  } else {
    Serial.print(" | Periodo: ");
    Serial.print(period_us[idx]);
    Serial.print(" us | Frec: ");
    Serial.print(freq_hz[idx], 2);
    Serial.print(" Hz | HIGH: ");
    Serial.print(high_us[idx]);
    Serial.print(" us | LOW: ");
    Serial.print(low_us[idx]);
    Serial.print(" us | Duty: ");
    Serial.print(duty_percent[idx], 1);
    Serial.println("%");
  }
}