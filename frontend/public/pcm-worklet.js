// AudioWorklet 采集器：每帧复制输入声道 0，连同 rms 转移给主线程。
// CSP script-src 'self' 禁止 blob worker，所以必须是 public/ 下的独立文件。
class PcmCapture extends AudioWorkletProcessor {
  process(inputs) {
    const ch = inputs[0] && inputs[0][0]
    if (ch && ch.length > 0) {
      const pcm = new Float32Array(ch.length)   // process 复用 ch 的底层内存，必须复制
      pcm.set(ch)
      let sum = 0
      for (let i = 0; i < ch.length; i++) sum += ch[i] * ch[i]
      this.port.postMessage({ pcm, rms: Math.sqrt(sum / ch.length) }, [pcm.buffer])
    }
    return true
  }
}

registerProcessor('pcm-capture', PcmCapture)
