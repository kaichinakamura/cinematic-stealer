import numpy as np
from skimage.exposure import match_histograms
from skimage.color import rgb2lab, lab2rgb
from PIL import Image

class ColorGradingEngine:
    def process(self, target_img: Image.Image, reference_img: Image.Image, intensity: float = 1.0, preserve_luminance: bool = True) -> Image.Image:
        """
        preserve_luminance=True の場合、LAB色空間で処理を行い、
        L(輝度)チャンネルは元画像を維持し、AB(色)チャンネルのみマッチングさせる。
        """
        # 1. RGB変換
        target_rgb = target_img.convert('RGB')
        ref_rgb = reference_img.convert('RGB')
        
        target_arr = np.array(target_rgb)
        ref_arr = np.array(ref_rgb)

        if preserve_luminance:
            # --- LABモード: 色情報だけを転写する (白飛び防止) ---
            
            # RGB -> LAB変換
            # scikit-imageのrgb2labは float64 (0-100, -128-127) を返す
            target_lab = rgb2lab(target_arr)
            ref_lab = rgb2lab(ref_arr)
            
            # 結果格納用の配列作成（元画像のL, a, bをコピー）
            matched_lab = target_lab.copy()
            
            # aチャンネル(赤-緑成分)のマッチング
            matched_lab[..., 1] = match_histograms(target_lab[..., 1], ref_lab[..., 1])
            
            # bチャンネル(青-黄成分)のマッチング
            matched_lab[..., 2] = match_histograms(target_lab[..., 2], ref_lab[..., 2])
            
            # Lチャンネル(明度)は target_lab[..., 0] のまま何もしない = 元のコントラストを維持！
            
            # LAB -> RGB変換 (範囲外の値が出ることがあるのでclipする)
            matched_arr = lab2rgb(matched_lab)
            # 0.0-1.0で返ってくるので 0-255のuint8に戻す
            matched_arr = (np.clip(matched_arr, 0, 1) * 255).astype('uint8')
            
        else:
            # --- Standardモード: 従来どおりRGBすべてをマッチング (コントラストも変わる) ---
            matched_arr = match_histograms(target_arr, ref_arr, channel_axis=-1)
            matched_arr = matched_arr.astype('uint8')

        # PIL画像化
        matched_img = Image.fromarray(matched_arr)

        # 4. ブレンド処理 (Intensity)
        if intensity == 1.0:
            return matched_img
        elif intensity == 0.0:
            return target_rgb
        else:
            return Image.blend(target_rgb, matched_img, intensity)

    def apply_to_hald(self, hald_img: Image.Image, reference_img: Image.Image, intensity: float = 1.0, preserve_luminance: bool = True) -> Image.Image:
        return self.process(hald_img, reference_img, intensity, preserve_luminance)