// 택트 스위치(sw1, sw2)으로 단색 LED(led1, led2) 제어. 
// 가변저항(Poten)으로 RGB LED 제어.

const int potPin = A5;

// RGB LED 모듈
const int redPin = 11;
const int greenPin = 12;
const int bluePin = 13;

// 택트 스위치
const int sw1 = 6;
const int sw2 = 7;

// 단색 LED
const int led1 = 9;
const int led2 = 10;

// 공통 음극형: false, 공통 양극형: true
const bool commonAnode = false;

// 빨, 주, 노, 초, 파, 남, 보
const int colors[7][3] = {
  {255,   0,   0},
  {255,  140,   0},
  {255, 255,   0},
  {  0, 205,   0},
  {  0, 191, 255},
  {  0,   0, 139},
  { 75,   0, 130}
};

float filteredPot;
float currentColor[3];

unsigned long lastUpdate = 0;

void setup() {
  pinMode(redPin, OUTPUT);
  pinMode(greenPin, OUTPUT);
  pinMode(bluePin, OUTPUT);

  pinMode(sw1, INPUT_PULLUP);
  pinMode(sw2, INPUT_PULLUP);

  pinMode(led1, OUTPUT);
  pinMode(led2, OUTPUT);

  filteredPot = analogRead(potPin);

  for (int i = 0; i < 3; i++) {
    currentColor[i] = getTargetColor(i);
  }

  writeColor();
}

void loop() {
  // 버튼을 누르는 동안 단색 LED 켜기
  digitalWrite(led1, digitalRead(sw1) == LOW ? HIGH : LOW);
  digitalWrite(led2, digitalRead(sw2) == LOW ? HIGH : LOW);

  // RGB는 5ms마다 갱신
  unsigned long now = millis();

  if (now - lastUpdate >= 5) {
    lastUpdate = now;

    // 가변저항 입력의 흔들림 완화
    filteredPot += (analogRead(potPin) - filteredPot) * 0.08f;

    // 목표 색상까지 서서히 이동
    for (int i = 0; i < 3; i++) {
      float target = getTargetColor(i);
      currentColor[i] += (target - currentColor[i]) * 0.12f;
    }

    writeColor();
  }
}

// 가변저항 위치에 해당하는 색상 계산
float getTargetColor(int channel) {
  float position = filteredPot * 6.0f / 1023.0f;
  int section = (int)position;

  if (section >= 6) {
    return colors[6][channel];
  }

  float ratio = position - section;

  return colors[section][channel]
       + (colors[section + 1][channel] - colors[section][channel])
       * ratio;
}

void writeColor() {
  int red   = constrain((int)(currentColor[0] + 0.5f), 0, 255);
  int green = constrain((int)(currentColor[1] + 0.5f), 0, 255);
  int blue  = constrain((int)(currentColor[2] + 0.5f), 0, 255);

  if (commonAnode) {
    red = 255 - red;
    green = 255 - green;
    blue = 255 - blue;
  }

  analogWrite(redPin, red);
  analogWrite(greenPin, green);
  analogWrite(bluePin, blue);
}