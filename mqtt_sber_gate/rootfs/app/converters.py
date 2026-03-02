import colorsys

def sber_hsv_to_rgb(h_sber: int, s_sber: int, v_sber: int) -> tuple[int, int, int]:
    """
    Convert Sber HSV (h:0-360, s:0-1000, v:100-1000) to RGB (0-255).
    """
    h = h_sber / 360.0
    s = s_sber / 1000.0
    v = v_sber / 1000.0
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    return int(r * 255), int(g * 255), int(b * 255)

def rgb_to_sber_hsv(r: int, g: int, b: int) -> tuple[int, int, int]:
    """
    Convert RGB (0-255) to Sber HSV (h:0-360, s:0-1000, v:100-1000).
    """
    r_norm = r / 255.0
    g_norm = g / 255.0
    b_norm = b / 255.0
    h, s, v = colorsys.rgb_to_hsv(r_norm, g_norm, b_norm)
    
    h_sber = int(h * 360)
    s_sber = int(s * 1000)
    v_sber = int(v * 1000)
    
    # Sber spec: v must be 100-1000
    v_sber = max(100, min(1000, v_sber))
    
    return h_sber, s_sber, v_sber

def ha_brightness_to_sber(ha_val):
    """
    Convert HA brightness (0-255) to Sber brightness (50-1000).
    """
    if ha_val is None:
        return 50
    return round(50 + (float(ha_val) / 255.0) * 950)

def sber_brightness_to_ha(sber_val):
    """
    Convert Sber brightness (50-1000) to HA brightness (0-255).
    """
    if sber_val is None:
        return 0
    val = round(((float(sber_val) - 50) / 950.0) * 255)
    return max(0, min(255, val))

def ha_temp_to_sber(mireds: int) -> int:
    """
    Convert HA color temp (mireds 153-500) to Sber temp (0-1000).
    Sber: 0 - Warm, 1000 - Cold.
    HA: 153 - Cold, 500 - Warm.
    """
    if mireds is None:
        return 0
    
    # Normalizing HA value (0.0 - Cold, 1.0 - Warm)
    normalized = (float(mireds) - 153) / (500 - 153)
    
    # Inverting for Sber (0 - Warm, 1000 - Cold)
    # If HA is Cold (153 -> 0.0), Sber should be Cold (1000)
    # If HA is Warm (500 -> 1.0), Sber should be Warm (0)
    val = round((1.0 - normalized) * 1000)
    return max(0, min(1000, val))

def sber_temp_to_ha(sber_val: int) -> int:
    """
    Convert Sber temp (0-1000) to HA color temp (mireds 153-500).
    Sber: 0 - Warm, 1000 - Cold.
    HA: 153 - Cold, 500 - Warm.
    """
    if sber_val is None:
        return 153
        
    # Normalizing Sber value (0.0 - Warm, 1.0 - Cold)
    normalized = float(sber_val) / 1000.0
    
    # Inverting for HA
    # If Sber is Warm (0 -> 0.0), HA should be Warm (500)
    # If Sber is Cold (1000 -> 1.0), HA should be Cold (153)
    val = round(500 - (normalized * (500 - 153)))
    return max(153, min(500, val))
