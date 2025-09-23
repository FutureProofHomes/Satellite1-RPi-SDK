# tests/test_xmos_firmware_parse.py
from satellite1.sat1_hat import XMOS

def test_fw_from_bytes_parses():
    x = XMOS()
    assert x._fw_from_bytes(bytes([1,2,3,0,0])) == "v1.2.3"
    assert x._fw_from_bytes(bytes([1,2,3,1,5])) == "v1.2.3-alpha.5"
