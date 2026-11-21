using System.Runtime.InteropServices;
using System.Text;

namespace CentreControle.App;

/// <summary>
/// Mixeur audio basse latence (winmm waveOut en flux continu 48 kHz stereo).
/// Le flux reste ouvert avec du silence numerique entre les clics afin d'eviter
/// le reveil WASAPI / fondu anti-pop Windows qui avale les impulsions courtes (&lt; 20 ms).
/// </summary>
public static class SoundHelper
{
    private const uint WAVE_MAPPER = 0xFFFFFFFF;
    private const uint CALLBACK_EVENT = 0x00050000;
    private const uint WHDR_DONE = 0x00000001;

    private const int SampleRate = 48000;
    private const int Channels = 2;
    private const int FramesPerBuffer = 384; // 8 ms par tampon
    private const int SamplesPerBuffer = FramesPerBuffer * Channels;
    private const int BytesPerBuffer = SamplesPerBuffer * sizeof(short);
    private const int BufferCount = 3;

    [StructLayout(LayoutKind.Sequential, Pack = 1)]
    private struct WAVEFORMATEX
    {
        public ushort wFormatTag;
        public ushort nChannels;
        public uint nSamplesPerSec;
        public uint nAvgBytesPerSec;
        public ushort nBlockAlign;
        public ushort wBitsPerSample;
        public ushort cbSize;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct WAVEHDR
    {
        public IntPtr lpData;
        public uint dwBufferLength;
        public uint dwBytesRecorded;
        public IntPtr dwUser;
        public uint dwFlags;
        public uint dwLoops;
        public IntPtr lpNext;
        public IntPtr reserved;
    }

    [DllImport("winmm.dll")]
    private static extern uint waveOutOpen(out IntPtr phwo, uint uDeviceID, ref WAVEFORMATEX pwfx, IntPtr dwCallback, IntPtr dwInstance, uint fdwOpen);

    [DllImport("winmm.dll")]
    private static extern uint waveOutPrepareHeader(IntPtr hwo, IntPtr pwh, uint cbwh);

    [DllImport("winmm.dll")]
    private static extern uint waveOutUnprepareHeader(IntPtr hwo, IntPtr pwh, uint cbwh);

    [DllImport("winmm.dll")]
    private static extern uint waveOutWrite(IntPtr hwo, IntPtr pwh, uint cbwh);

    [DllImport("winmm.dll")]
    private static extern uint waveOutReset(IntPtr hwo);

    [DllImport("winmm.dll")]
    private static extern uint waveOutClose(IntPtr hwo);

    private sealed class ActiveVoice
    {
        public required short[] Samples;
        public int Offset;
    }

    private sealed class BufferSlot
    {
        public IntPtr DataPtr;
        public IntPtr HdrPtr;
        public bool Prepared;
    }

    private static readonly object _lifecycleLock = new();
    private static readonly object _mixLock = new();
    private static readonly List<ActiveVoice> _voices = new();
    private static readonly uint _hdrSize = (uint)Marshal.SizeOf<WAVEHDR>();

    private static short[]? _clickDownSamples;
    private static short[]? _clickUpSamples;

    private static volatile bool _running;
    private static AutoResetEvent? _wakeEvent;
    private static Thread? _audioThread;

    public static void Initialize(string baseDir)
    {
        lock (_lifecycleLock)
        {
            ShutdownCore();

            _clickDownSamples = LoadWavPcm16(Path.Combine(baseDir, "assets", "click_down.wav"));
            _clickUpSamples = LoadWavPcm16(Path.Combine(baseDir, "assets", "click_up.wav"));

            if (_clickDownSamples is null && _clickUpSamples is null)
                return;

            _wakeEvent = new AutoResetEvent(false);
            _running = true;
            _audioThread = new Thread(AudioLoop)
            {
                Name = "CentreControleAudioMixer",
                IsBackground = true,
                Priority = ThreadPriority.AboveNormal,
            };
            _audioThread.Start();
        }
    }

    public static void PlayClickDown() => Trigger(_clickDownSamples);

    public static void PlayClickUp() => Trigger(_clickUpSamples);

    private static void Trigger(short[]? clip)
    {
        if (clip is null || clip.Length == 0 || !_running)
            return;
        lock (_mixLock)
        {
            if (_voices.Count >= 8)
                _voices.RemoveAt(0);
            _voices.Add(new ActiveVoice { Samples = clip, Offset = 0 });
        }
    }

    public static void Shutdown()
    {
        lock (_lifecycleLock)
        {
            ShutdownCore();
        }
    }

    private static void ShutdownCore()
    {
        _running = false;
        try { _wakeEvent?.Set(); } catch { }
        try { _audioThread?.Join(500); } catch { }
        _audioThread = null;
        try { _wakeEvent?.Dispose(); } catch { }
        _wakeEvent = null;
        lock (_mixLock)
        {
            _voices.Clear();
        }
    }

    private static void AudioLoop()
    {
        var mixBuf = new short[SamplesPerBuffer];
        var slots = new BufferSlot[BufferCount];
        for (int i = 0; i < BufferCount; i++)
        {
            slots[i] = new BufferSlot
            {
                DataPtr = Marshal.AllocHGlobal(BytesPerBuffer),
                HdrPtr = Marshal.AllocHGlobal((int)_hdrSize),
            };
        }

        IntPtr hwo = IntPtr.Zero;
        try
        {
            while (_running)
            {
                if (hwo == IntPtr.Zero)
                {
                    if (!TryOpenAndPrime(slots, mixBuf, out hwo))
                    {
                        Thread.Sleep(500);
                        continue;
                    }
                }

                _wakeEvent?.WaitOne(40);
                if (!_running) break;

                bool deviceError = false;
                for (int i = 0; i < BufferCount; i++)
                {
                    var hdr = Marshal.PtrToStructure<WAVEHDR>(slots[i].HdrPtr);
                    if ((hdr.dwFlags & WHDR_DONE) == 0)
                        continue;

                    MixInto(mixBuf);
                    Marshal.Copy(mixBuf, 0, slots[i].DataPtr, SamplesPerBuffer);
                    uint rc = waveOutWrite(hwo, slots[i].HdrPtr, _hdrSize);
                    if (rc != 0)
                    {
                        deviceError = true;
                        break;
                    }
                }

                if (deviceError)
                {
                    CloseDevice(ref hwo, slots);
                    Thread.Sleep(250);
                }
            }
        }
        finally
        {
            CloseDevice(ref hwo, slots);
            for (int i = 0; i < BufferCount; i++)
            {
                if (slots[i].HdrPtr != IntPtr.Zero) Marshal.FreeHGlobal(slots[i].HdrPtr);
                if (slots[i].DataPtr != IntPtr.Zero) Marshal.FreeHGlobal(slots[i].DataPtr);
            }
        }
    }

    private static bool TryOpenAndPrime(BufferSlot[] slots, short[] mixBuf, out IntPtr hwo)
    {
        hwo = IntPtr.Zero;
        if (_wakeEvent is null) return false;

        var fmt = new WAVEFORMATEX
        {
            wFormatTag = 1, // PCM
            nChannels = Channels,
            nSamplesPerSec = SampleRate,
            nBlockAlign = Channels * sizeof(short),
            nAvgBytesPerSec = SampleRate * Channels * sizeof(short),
            wBitsPerSample = 16,
            cbSize = 0,
        };

        IntPtr evtHandle = _wakeEvent.SafeWaitHandle.DangerousGetHandle();
        if (waveOutOpen(out hwo, WAVE_MAPPER, ref fmt, evtHandle, IntPtr.Zero, CALLBACK_EVENT) != 0)
        {
            hwo = IntPtr.Zero;
            return false;
        }

        Array.Clear(mixBuf, 0, mixBuf.Length);
        for (int i = 0; i < BufferCount; i++)
        {
            Marshal.Copy(mixBuf, 0, slots[i].DataPtr, SamplesPerBuffer);
            var hdr = new WAVEHDR
            {
                lpData = slots[i].DataPtr,
                dwBufferLength = BytesPerBuffer,
            };
            Marshal.StructureToPtr(hdr, slots[i].HdrPtr, false);
            if (waveOutPrepareHeader(hwo, slots[i].HdrPtr, _hdrSize) != 0)
            {
                CloseDevice(ref hwo, slots);
                return false;
            }
            slots[i].Prepared = true;

            if (waveOutWrite(hwo, slots[i].HdrPtr, _hdrSize) != 0)
            {
                CloseDevice(ref hwo, slots);
                return false;
            }
        }

        return true;
    }

    private static void CloseDevice(ref IntPtr hwo, BufferSlot[] slots)
    {
        if (hwo == IntPtr.Zero) return;
        try
        {
            waveOutReset(hwo);
            for (int i = 0; i < slots.Length; i++)
            {
                if (slots[i].Prepared)
                {
                    waveOutUnprepareHeader(hwo, slots[i].HdrPtr, _hdrSize);
                    slots[i].Prepared = false;
                }
            }
            waveOutClose(hwo);
        }
        catch { }
        hwo = IntPtr.Zero;
    }

    private static void MixInto(short[] dst)
    {
        Array.Clear(dst, 0, dst.Length);
        lock (_mixLock)
        {
            if (_voices.Count == 0)
                return;

            for (int v = _voices.Count - 1; v >= 0; v--)
            {
                var voice = _voices[v];
                int remain = voice.Samples.Length - voice.Offset;
                int count = Math.Min(dst.Length, remain);
                for (int i = 0; i < count; i++)
                {
                    int sum = dst[i] + voice.Samples[voice.Offset + i];
                    if (sum > short.MaxValue) sum = short.MaxValue;
                    else if (sum < short.MinValue) sum = short.MinValue;
                    dst[i] = (short)sum;
                }
                voice.Offset += count;
                if (voice.Offset >= voice.Samples.Length)
                    _voices.RemoveAt(v);
            }
        }
    }

    private static short[]? LoadWavPcm16(string path)
    {
        try
        {
            if (!File.Exists(path)) return null;
            var bytes = File.ReadAllBytes(path);
            if (bytes.Length < 44) return null;
            if (bytes[0] != 'R' || bytes[1] != 'I' || bytes[2] != 'F' || bytes[3] != 'F') return null;

            ushort channels = 0, bits = 0;
            uint rate = 0;
            byte[]? pcm = null;

            int pos = 12;
            while (pos + 8 <= bytes.Length)
            {
                string id = Encoding.ASCII.GetString(bytes, pos, 4);
                int size = BitConverter.ToInt32(bytes, pos + 4);
                pos += 8;
                if (size < 0 || pos + size > bytes.Length) break;

                if (id == "fmt " && size >= 16)
                {
                    channels = BitConverter.ToUInt16(bytes, pos + 2);
                    rate = BitConverter.ToUInt32(bytes, pos + 4);
                    bits = BitConverter.ToUInt16(bytes, pos + 14);
                }
                else if (id == "data")
                {
                    pcm = new byte[size];
                    Buffer.BlockCopy(bytes, pos, pcm, 0, size);
                }
                pos += size + (size & 1);
            }

            if (pcm is null || bits != 16 || channels == 0 || rate == 0)
                return null;

            int sampleCount = pcm.Length / 2;
            var raw = new short[sampleCount];
            Buffer.BlockCopy(pcm, 0, raw, 0, sampleCount * 2);

            if (channels == Channels && rate == SampleRate)
                return raw;

            // Conversion mono -> stereo si besoin
            if (channels == 1 && rate == SampleRate)
            {
                var stereo = new short[sampleCount * 2];
                for (int i = 0; i < sampleCount; i++)
                {
                    stereo[i * 2] = raw[i];
                    stereo[i * 2 + 1] = raw[i];
                }
                return stereo;
            }

            return raw;
        }
        catch
        {
            return null;
        }
    }
}
