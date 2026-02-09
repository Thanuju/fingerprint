import os
from PIL import Image
import numpy as np
from sklearn.ensemble import RandomForestClassifier
import joblib

DATA_DIR = "data"
FPRINT_DIR = os.path.join(DATA_DIR, "fingerprint")
NOT_DIR = os.path.join(DATA_DIR, "not_fingerprint")
MODEL_OUT = "fingerprint_model.pkl"
IMG_SIZE = (128, 128)

def load_images(folder, label):
    X = []
    y = []
    for fname in os.listdir(folder):
        path = os.path.join(folder, fname)
        if not fname.lower().endswith((".jpg", ".png", ".jpeg")):
            continue
        try:
            img = Image.open(path).convert("L").resize(IMG_SIZE)
            arr = np.array(img, dtype=np.float32) / 255.0
            X.append(arr.flatten())
            y.append(label)
        except Exception as e:
            print("Skipping:", path, "Error:", e)
    return X, y

def main():
    # Load fingerprint images
    X1, y1 = load_images(FPRINT_DIR, 1)
    # Load non-fingerprint images
    X2, y2 = load_images(NOT_DIR, 0)

    X = np.array(X1 + X2)
    y = np.array(y1 + y2)

    print("Loaded", len(y), "images.")

    clf = RandomForestClassifier(n_estimators=300, random_state=42)
    clf.fit(X, y)

    joblib.dump(clf, MODEL_OUT)
    print("Model saved as", MODEL_OUT)

if __name__ == "__main__":
    main()
