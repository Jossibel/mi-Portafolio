const int leds[] = {2, 3, 4, 5, 6, 7};
const int boton = 8;

int patronActual = 0;

void setup() {
  for (int i = 0; i < 6; i++) {
    pinMode(leds[i], OUTPUT);
  }

  pinMode(boton, INPUT_PULLUP);
  randomSeed(analogRead(0)); // para aleatorio
}

void loop() {
  leerBoton();

  switch (patronActual) {
    case 0: patronSecuencia(); break;
    case 1: patronPersecucion(); break;
    case 2: patronParpadeo(); break;
    case 3: patronAleatorio(); break;
    case 4: patronOnda(); break;
  }
}

// -------- FUNCIONES --------

void leerBoton() {
  if (digitalRead(boton) == LOW) {
    patronActual = random(0, 5); // 0 a 4
    delay(300); // anti rebote simple
  }
}

void apagarTodo() {
  for (int i = 0; i < 6; i++) {
    digitalWrite(leds[i], LOW);
  }
}

// Patrón 0
void patronSecuencia() {
  for (int i = 0; i < 6; i++) {
    digitalWrite(leds[i], HIGH);
    delay(100);
    digitalWrite(leds[i], LOW);
  }
}

// Patrón 1
void patronPersecucion() {
  for (int i = 0; i < 6; i++) {
    apagarTodo();
    digitalWrite(leds[i], HIGH);
    delay(100);
  }
}

// Patrón 2
void patronParpadeo() {
  for (int i = 0; i < 6; i++) {
    digitalWrite(leds[i], HIGH);
  }
  delay(200);
  apagarTodo();
  delay(200);
}

// Patrón 3
void patronAleatorio() {
  int led = random(0, 6);
  apagarTodo();
  digitalWrite(leds[led], HIGH);
  delay(150);
}

// Patrón 4
void patronOnda() {
  for (int i = 0; i < 6; i++) {
    digitalWrite(leds[i], HIGH);
    delay(80);
  }
  for (int i = 5; i >= 0; i--) {
    digitalWrite(leds[i], LOW);
    delay(80);
  }
}