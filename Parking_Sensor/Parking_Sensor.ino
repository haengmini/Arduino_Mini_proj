const int echoPin = 7;
const int trigPin = 8;
const int Buzzer = 5;

unsigned long lastMeasure = 0;
unsigned long lastBeep = 0;

int beepInterval = 0;
bool continuousAlarm = false;
bool wasContinuous = false;

void setup() {
  pinMode(trigPin, OUTPUT);
  pinMode(echoPin, INPUT);
  pinMode(Buzzer, OUTPUT);

  digitalWrite(trigPin, LOW);
  Serial.begin(9600);
}

void loop() {
  unsigned long now = millis();

  if (now - lastMeasure >= 60) {
    lastMeasure = now;

    digitalWrite(trigPin, LOW);
    delayMicroseconds(2);
    digitalWrite(trigPin, HIGH);
    delayMicroseconds(10);
    digitalWrite(trigPin, LOW);

    unsigned long duration = pulseIn(echoPin, HIGH, 25000UL);

    continuousAlarm = false;
    beepInterval = 0;

    if (duration == 0) {
      Serial.println("No echo");
    } else {
      float distance = duration * 0.0343f / 2.0f;

      Serial.print("Distance: ");
      Serial.print(distance, 1);
      Serial.println(" cm");

      if (distance <= 5) {
        continuousAlarm = true;
      } else if (distance <= 10) {
        beepInterval = 150;
      } else if (distance <= 20) {
        beepInterval = 300;
      } else if (distance <= 30) {
        beepInterval = 600;
      }
    }

    // 연속음에서 벗어나거나 감지 범위를 벗어나면 끄기
    if (!continuousAlarm &&
        (wasContinuous || beepInterval == 0)) {
      noTone(Buzzer);
    }

    wasContinuous = continuousAlarm;
  }

  now = millis();

  if (continuousAlarm) {
    tone(Buzzer, 2000);
  } else if (beepInterval > 0) {
    if (now - lastBeep >= (unsigned long)beepInterval) {
      lastBeep = now;
      tone(Buzzer, 2000, 70);
    }
  }
}