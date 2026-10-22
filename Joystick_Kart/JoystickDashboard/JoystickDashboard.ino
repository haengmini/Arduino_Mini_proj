const int xPin = A0;
const int yPin = A1;
const int buttonPin = 2;
unsigned long lastSend = 0;

void setup() {
  pinMode(buttonPin, INPUT_PULLUP);
  Serial.begin(115200);
}

void loop() {
  if (millis() - lastSend >= 20) {
    lastSend = millis();
    Serial.print(analogRead(xPin));
    Serial.print(',');
    Serial.print(analogRead(yPin));
    Serial.print(',');
    Serial.println(digitalRead(buttonPin));
  }
}
