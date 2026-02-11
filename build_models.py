import tensorflow as tf
from tensorflow.keras import layers, models
import os

# CONFIG
ASSET_DIR = os.path.join("hospital_ai_assets", "models")
if not os.path.exists(ASSET_DIR): os.makedirs(ASSET_DIR)

def create_cnn_model(name, num_classes=2):
    print(f"🛠️  Building Real CNN for {name}...")
    model = models.Sequential([
        # Layer 1: Convolution (The Eye - detects edges/shapes)
        layers.Conv2D(32, (3, 3), activation='relu', input_shape=(224, 224, 3)),
        layers.MaxPooling2D((2, 2)),
        
        # Layer 2: Convolution (Detects textures)
        layers.Conv2D(64, (3, 3), activation='relu'),
        layers.MaxPooling2D((2, 2)),
        
        # Layer 3: Convolution (Detects complex patterns)
        layers.Conv2D(64, (3, 3), activation='relu'),
        
        # Flatten: Convert 2D images to 1D list of numbers
        layers.Flatten(),
        
        # Dense Layers: The Decision Making
        layers.Dense(64, activation='relu'),
        layers.Dense(1, activation='sigmoid') # Binary Output (0 or 1)
    ])
    
    model.compile(optimizer='adam',
                  loss='binary_crossentropy',
                  metrics=['accuracy'])
    
    save_path = os.path.join(ASSET_DIR, f"{name}.h5")
    model.save(save_path)
    print(f"✅ Saved Real Model: {save_path}")

# --- BUILD THE MODELS ---
create_cnn_model("pneumonia_model")
create_cnn_model("brain_tumor_model")

print("\n" + "="*50)
print("SUCCESS: Real Neural Networks created.")
print("NOTE: These are UNTRAINED brains. They have the structure")
print("to see, but they haven't 'learned' from data yet.")
print("They will give real prediction scores based on pixels.")
print("="*50)