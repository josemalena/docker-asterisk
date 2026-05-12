#!/app/bin/python3
import os
import sys
import random
#import openai
from pydub import AudioSegment

# Start program
callerId = '1001'
filepath = "/var/lib/asterisk/sounds/custom"


while True: 
    n = random.randint(1, 9999999999) # generate a random number between 1 and 9999999999
    n = int(callerId)
    filename = str(n).zfill(10) # pad with zeros and add extension
    # Load the audio file
    sound = AudioSegment.from_file(f"{filepath}/{filename}_response.mp3", format="mp3")
    # Set the sample rate to 8kHz
    sound = sound.set_frame_rate(8000)
    # Set the number of channels to mono
    sound = sound.set_channels(1)
    # Export the audio file as a WAV file
    sound.export(f"{filepath}/{filename}_response.wav", format="wav")
    exit(0)
