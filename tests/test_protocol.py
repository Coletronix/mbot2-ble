from mbot2 import protocol as P

# Bytes observed on the wire from mBlock 5 (published captures).
CAPTURED_PING = "f3f603000d00000df4"
CAPTURED_EXEC1 = "f3202d002804000027007472793a0a20202020696d706f727420636f6e6669670a6578636570743a0a2020202070617373b5f4"
CAPTURED_EXEC2 = (
    "f33c49002804000043007472793a0a20202020636f6e6669672e77726974655f636f6e66696728227265706c5f656e61626c65"
    "222c2046616c7365290a6578636570743a0a202020207061737389f4"
)


def test_preamble_matches_mblock():
    assert P.UPLOAD_MODE.hex() == CAPTURED_PING
    assert P.EXEC_IMPORT_CONFIG.hex() == CAPTURED_EXEC1
    assert P.EXEC_REPL_OFF.hex() == CAPTURED_EXEC2


def test_makeblock_lib_script_frame():
    # makeblock PyPI package, HalocodePackData: run-with-response "cyberpi.get_bri()" idx 1
    assert P.script("cyberpi.get_bri()", P.SCRIPT_EVAL, 1).hex() == (
        "f30a1700280101001100637962657270692e6765745f627269282984f4"
    )


def test_xor32():
    assert P.xor32(b"\x01\x00\x00\x00\x02\x00\x00\x00") == 3
    assert P.xor32(b"\xff") == 0xFF  # zero padded


def test_padding_and_blocks():
    for n in [1, 4, 5, 79, 80, 84, 85, 163, 164, 1000]:
        data = P.pad_for_wire(b"x" * n)
        assert len(data) % 80 == 4 and len(data) >= n
        parts = P.blocks(data)
        assert b"".join(c for _, c in parts) == data
        assert all(len(c) == 80 for _, c in parts[:-1]) and len(parts[-1][1]) == 4
        assert [o for o, _ in parts] == sorted(o for o, _ in parts)


def test_file_frames_and_reader_roundtrip():
    data = P.pad_for_wire(b"print(1)\n")
    frames = [P.file_header(data, P.staging_path())] + [P.file_block(o, c) for o, c in P.blocks(data)]
    got, text = [], []
    r = P.FrameReader(got.append, text.append)
    stream = b"hello\r\n" + b"".join(frames) + b">>> "
    for i in range(0, len(stream), 7):  # arrive in odd-sized pieces
        r.feed(stream[i : i + 7])
    assert len(got) == len(frames) and all(f.is_file_ack() for f in got)
    assert b"".join(text) == b"hello\r\n>>> "
    hdr = got[0].body
    assert hdr[:4] == b"\x01\x00\x5e\x01" and hdr.endswith(b"/flash/_xx_main.py")


def test_script_reply_decoding():
    # exact reply the robot sent to eval("1+1") with idx 10
    reply = b"\xf3\x02\x0f\x00(\x01\n\x00\t\x00{\"ret\":2}/\xf4"
    got = []
    P.FrameReader(got.append, lambda b: None).feed(reply)
    assert got[0].is_script_reply() and got[0].script_result() == 2
