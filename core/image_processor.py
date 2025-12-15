import numpy as np
from skimage.exposure import match_histograms
from skimage.color import rgb2lab, lab2rgb
from PIL import Image

class ColorGradingEngine:
    def _apply_reinhard(self, target_arr, ref_arr):
        """
        Reinhard法によるカラー転写ロジック (Natural Mode)
        LAB色空間における各チャンネルの平均(Mean)と標準偏差(Std)を一致させる。
        """
        # 1. LAB変換 (float64)
        t_lab = rgb2lab(target_arr)
        r_lab = rgb2lab(ref_arr)

        # 2. 統計量の計算 (各チャンネルごと)
        # axis=(0, 1) で画像の縦横全体の平均・標準偏差を取る
        t_mean = np.mean(t_lab, axis=(0, 1))
        t_std  = np.std(t_lab, axis=(0, 1))
        
        r_mean = np.mean(r_lab, axis=(0, 1))
        r_std  = np.std(r_lab, axis=(0, 1))

        # 3. 転写 (標準化 -> 参照画像の分布へ復元)
        # ゼロ除算回避のため eps を足す
        eps = 1e-6
        result_lab = (t_lab - t_mean) * (r_std / (t_std + eps)) + r_mean

        # 4. RGBに戻す
        # lab2rgbは内部で範囲チェックを行うが、念のため
        result_rgb = lab2rgb(result_lab)
        
        # 0.0-1.0 を 0-255 に変換してクリップ
        return (np.clip(result_rgb, 0, 1) * 255).astype('uint8')

    def process(self, target_img: Image.Image, reference_img: Image.Image, 
                intensity: float = 1.0, 
                preserve_luminance: bool = True,
                method: str = "histogram") -> Image.Image: # method引数を追加
        """
        method: "histogram" (Dramatic) or "reinhard" (Natural)
        """
        target_rgb = target_img.convert('RGB')
        ref_rgb = reference_img.convert('RGB')
        
        target_arr = np.array(target_rgb)
        ref_arr = np.array(ref_rgb)
        
        matched_arr = None

        # --- A. Reinhard Mode (Natural) ---
        if method == "reinhard":
            # Reinhardは元々LAB空間を使う手法なので、preserve_luminanceの概念は
            # 「Lチャンネルの統計量をいじるかどうか」になるが、
            # シンプルに「全体適用」か「輝度維持」かで分岐させる
            
            if preserve_luminance:
                # 色(AB)だけReinhard適用、Lは元画像のまま
                # 手動でLAB分解して合成する
                t_lab = rgb2lab(target_arr)
                
                # 色味だけ転写した画像を生成
                full_reinhard = self._apply_reinhard(target_arr, ref_arr)
                r_lab_applied = rgb2lab(full_reinhard)
                
                # Lは元画像(t_lab)、ABは適用後(r_lab_applied)を使う
                combined_lab = t_lab.copy()
                combined_lab[..., 1] = r_lab_applied[..., 1] # A
                combined_lab[..., 2] = r_lab_applied[..., 2] # B
                
                matched_arr = (np.clip(lab2rgb(combined_lab), 0, 1) * 255).astype('uint8')
            else:
                # 輝度も含めてガッツリ統計合わせ
                matched_arr = self._apply_reinhard(target_arr, ref_arr)

        # --- B. Histogram Mode (Dramatic) ---
        else:
            if preserve_luminance:
                target_lab = rgb2lab(target_arr)
                ref_lab = rgb2lab(ref_arr)
                matched_lab = target_lab.copy()
                
                # A, Bチャンネルのみマッチング
                matched_lab[..., 1] = match_histograms(target_lab[..., 1], ref_lab[..., 1])
                matched_lab[..., 2] = match_histograms(target_lab[..., 2], ref_lab[..., 2])
                
                matched_arr = lab2rgb(matched_lab)
                matched_arr = (np.clip(matched_arr, 0, 1) * 255).astype('uint8')
            else:
                matched_arr = match_histograms(target_arr, ref_arr, channel_axis=-1)
                matched_arr = matched_arr.astype('uint8')

        # 結果をPIL化
        matched_img = Image.fromarray(matched_arr)

        # Intensityブレンド
        if intensity == 1.0:
            return matched_img
        elif intensity == 0.0:
            return target_rgb
        else:
            return Image.blend(target_rgb, matched_img, intensity)

    def apply_to_hald(self, hald_img: Image.Image, reference_img: Image.Image, 
                      intensity: float = 1.0, 
                      preserve_luminance: bool = True,
                      method: str = "histogram") -> Image.Image:
        # メソッド引数をパススルー
        return self.process(hald_img, reference_img, intensity, preserve_luminance, method)