import os
import re
import torch
import torchaudio as ta
from chatterbox.tts_turbo import ChatterboxTurboTTS
import torchaudio.functional as F
# =========================
# Config
# =========================

DEVICE = "cpu"  # "cpu" or "mps"
AUDIO_PROMPT = "steve.wav"
OUTPUT_FILE = "final_output.wav"
TEMP_DIR = "temp_batches"

MAX_SPEECH_TOKENS = 900
CFG_WEIGHT = 0.35

# =========================
# Load Model
# =========================

model = ChatterboxTurboTTS.from_pretrained(device=DEVICE)

# =========================
# Utilities
# =========================

def estimate_speech_tokens(text_token_count, cfg_weight=0.35):
    """
    Approximate speech tokens from text tokens.
    Chatterbox speech tokens are usually ~6-8x text tokens.
    """
    speech_tokens = text_token_count * 7  # empirical average
    if cfg_weight > 0:
        speech_tokens *= 2
    return speech_tokens


def estimate_tokens(text):
    return len(text.split())  # lightweight fallback


def split_text_into_sentences(text):
    chunks = re.findall(r"[^.!?…]+(?:\.{3}|…|[.!?])", text)
    sentences = [c.strip() for c in chunks if c.strip()]
    return sentences if sentences else [text]


def split_text_into_batches(text, max_speech_tokens=900):
    sentences = split_text_into_sentences(text)

    batches = []
    current_batch = ""
    current_tokens = 0

    for sentence in sentences:
        token_estimate = estimate_speech_tokens(len(sentence.split()), CFG_WEIGHT)

        if current_tokens + token_estimate > max_speech_tokens:
            if current_batch:
                batches.append(current_batch.strip())
                current_batch = ""
                current_tokens = 0

        current_batch += " " + sentence
        current_tokens += token_estimate

    if current_batch.strip():
        batches.append(current_batch.strip())

    return batches


def concat_audio_files(input_files, output_file, sample_rate):
    audio_segments = []

    for path in input_files:
        wav, sr = ta.load(path)

        if wav.shape[0] > 1:
            wav = wav.mean(dim=0, keepdim=True)

        if sr != sample_rate:
            resampler = ta.transforms.Resample(sr, sample_rate)
            wav = resampler(wav)

        audio_segments.append(wav)

    final_audio = torch.cat(audio_segments, dim=1)

    ta.save(output_file, final_audio, sample_rate)

    print(f"\nFinal audio saved: {output_file}")
    print(f"Duration: {final_audio.shape[1] / sample_rate:.2f} seconds")


# =========================
# Main TTS Function
# =========================

def generate_long_tts(text):

    os.makedirs(TEMP_DIR, exist_ok=True)

    estimated = estimate_tokens(text)
    print(f"Estimated text tokens: {estimated}")

    batches = split_text_into_batches(text, MAX_SPEECH_TOKENS)
    print(f"Split into {len(batches)} batches")

    batch_files = []

    for i, batch_text in enumerate(batches):
        print(f"\nGenerating batch {i+1}/{len(batches)}")

        wav = model.generate(
            batch_text,
            audio_prompt_path=AUDIO_PROMPT,
            exaggeration=0.4,
            temperature=0.9,
            cfg_weight=CFG_WEIGHT
        )
        batch_path = os.path.join(TEMP_DIR, f"batch_{i}.wav")
        ta.save(batch_path, wav, model.sr)

        batch_files.append(batch_path)

    concat_audio_files(batch_files, OUTPUT_FILE, model.sr)

    # Cleanup temp files
    for f in batch_files:
        os.remove(f)
    os.rmdir(TEMP_DIR)


# =========================
# Run
# =========================

text = """ The package had no sender, yet it carried a key that matched your own heartbeat. Alex sweeps the last dust mote; the clock ticks in sync. The doorbell rings. A weathered package sits on the cracked doormat, no label. Dr. Emily Porter, Harvard: 'The unknown mirrors our inner terror.' You can't ignore the echo. You've felt the weight of each pixel—your work demands perfection. Normal folks lock fears away; you can choose to face the unknown. The choice is yours; it's the first key today. But here's what they didn't know... The key hums louder ever as the clock rewinds. """

generate_long_tts(text)
