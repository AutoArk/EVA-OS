import pyaudio

p = pyaudio.PyAudio()

print(f"{'Index':<6} {'Name':<40} {'In/Out':<10} {'Rate'}")
print("-" * 70)

for i in range(p.get_device_count()):
    info = p.get_device_info_by_index(i)
    name = info.get('name')
    in_ch = info.get('maxInputChannels')
    out_ch = info.get('maxOutputChannels')
    rate = int(info.get('defaultSampleRate'))
    
    io_type = []
    if in_ch > 0: io_type.append("In")
    if out_ch > 0: io_type.append("Out")
    
    print(f"{i:<6} {name:<40} {'/'.join(io_type):<10} {rate}")

p.terminate()