import numpy as np
from skimage.exposure import match_histograms
from skimage.color import rgb2lab, lab2rgb
from sklearn.cluster import MiniBatchKMeans
from PIL import Image

class ColorGradingEngine:
    
    # --- 既存: Reinhard (Simple Mean/Std) ---
    def _apply_reinhard(self, target_arr, ref_arr):
        t_lab = rgb2lab(target_arr)
        r_lab = rgb2lab(ref_arr)
        
        # 軸ごとの単純な平均・分散合わせ
        t_mean = np.mean(t_lab, axis=(0, 1))
        t_std  = np.std(t_lab, axis=(0, 1))
        r_mean = np.mean(r_lab, axis=(0, 1))
        r_std  = np.std(r_lab, axis=(0, 1))
        
        eps = 1e-6
        result_lab = (t_lab - t_mean) * (r_std / (t_std + eps)) + r_mean
        
        return (np.clip(lab2rgb(result_lab), 0, 1) * 255).astype('uint8')

    # --- 新規: Covariance Transfer (3D Reinhard) ---
    def _apply_covariance(self, target_arr, ref_arr):
        """
        色の相関関係（共分散行列）を考慮した線形変換。
        Reinhard法よりも「色の混ざり具合」を正確に転写できる。
        Monge-Kantorovitch解の近似。
        """
        t_lab = rgb2lab(target_arr).reshape(-1, 3)
        r_lab = rgb2lab(ref_arr).reshape(-1, 3)

        # 共分散行列と平均の計算
        t_mean = np.mean(t_lab, axis=0)
        t_cov = np.cov(t_lab, rowvar=False)
        
        r_mean = np.mean(r_lab, axis=0)
        r_cov = np.cov(r_lab, rowvar=False)

        # 行列の平方根などを計算 (Cholesky分解 or 特異値分解)
        # A = T_cov^(-1/2), B = R_cov^(1/2)
        # 色変換: x' = (x - t_mean) * A * B + r_mean
        
        try:
            # 特異値分解(SVD)を用いて行列の平方根を求める（安定性のため）
            u_t, s_t, vh_t = np.linalg.svd(t_cov)
            # t_cov^(-1/2)
            s_t_inv_sqrt = np.diag(1.0 / np.sqrt(s_t + 1e-6))
            t_sqrt_inv = u_t @ s_t_inv_sqrt @ vh_t

            u_r, s_r, vh_r = np.linalg.svd(r_cov)
            # r_cov^(1/2)
            r_sqrt = u_r @ np.diag(np.sqrt(s_r)) @ vh_r

            # 変換行列 M = T^(-1/2) * R^(1/2)
            M = t_sqrt_inv @ r_sqrt
            
            # 適用
            matched_flat = (t_lab - t_mean) @ M + r_mean
            
            # 形状を戻してRGB化
            matched_lab = matched_flat.reshape(target_arr.shape)
            return (np.clip(lab2rgb(matched_lab), 0, 1) * 255).astype('uint8')
            
        except np.linalg.LinAlgError:
            # 計算失敗時は単純なReinhardにフォールバック
            return self._apply_reinhard(target_arr, ref_arr)

    # --- 新規: K-Means Clustering (Local Reinhard) ---
    def _apply_kmeans(self, target_arr, ref_arr, n_clusters=3):
        """
        画像をk個の領域（シャドウ・中間・ハイライト等）にクラスタリングし、
        それぞれの領域ごとにReinhard法を適用する。
        """
        # 高速化のため、学習は縮小画像で行う
        small_h, small_w = 100, 100
        
        t_lab_full = rgb2lab(target_arr)
        r_lab_full = rgb2lab(ref_arr)
        
        # 学習用データ作成 (L輝度のみでクラスタリングしたほうが自然な場合が多いが、今回は全色使う)
        # 高速化: MiniBatchKMeansを使用
        t_flat = t_lab_full.reshape(-1, 3)
        r_flat = r_lab_full.reshape(-1, 3)
        
        # サンプリング学習
        rng = np.random.RandomState(42)
        idx_t = rng.permutation(t_flat.shape[0])[:2000] # 2000ピクセルで学習
        idx_r = rng.permutation(r_flat.shape[0])[:2000]
        
        kmeans_t = MiniBatchKMeans(n_clusters=n_clusters, random_state=0, n_init=3).fit(t_flat[idx_t])
        kmeans_r = MiniBatchKMeans(n_clusters=n_clusters, random_state=0, n_init=3).fit(r_flat[idx_r])
        
        # クラスタを「輝度(L)」順にソートして対応付ける
        # (暗いクラスタは暗いクラスタへ、明るいクラスタは明るいクラスタへ)
        t_centers = kmeans_t.cluster_centers_
        r_centers = kmeans_r.cluster_centers_
        
        t_order = np.argsort(t_centers[:, 0]) # Lチャンネルでソート
        r_order = np.argsort(r_centers[:, 0])
        
        # 全ピクセルの所属クラスタを予測 (ここが少し重い)
        # 高速化: 画像を少し縮小してラベルマップを作り、リサイズする手もあるが
        # ここでは精度優先で全画素予測（重すぎる場合はリサイズ推奨）
        
        # メモリ節約のためダウンサンプリング予測アプローチを採用
        h, w, _ = target_arr.shape
        t_small = t_lab_full[::4, ::4, :].reshape(-1, 3) # 1/16の間引き
        labels_small = kmeans_t.predict(t_small)
        
        # ラベルマップを元のサイズに拡大 (Nearest Neighbor)
        from skimage.transform import resize
        labels_map = resize(labels_small.reshape(int(np.ceil(h/4)), int(np.ceil(w/4))), (h, w), order=0, preserve_range=True).astype(int)

        result_lab = np.zeros_like(t_lab_full)
        
        # 各クラスタごとにReinhard適用
        for i in range(n_clusters):
            # Targetのi番目のクラスタに対応するReferenceのクラスタ
            t_k = t_order[i]
            r_k = r_order[i]
            
            # マスク作成
            mask = (labels_map == t_k)
            if np.sum(mask) == 0: continue
            
            # 統計量計算
            t_pixels = t_lab_full[mask]
            
            # Reference側はそのクラスタに属するピクセル全体の統計を使う
            # (ピクセル単位の対応ではなく、統計的な対応)
            # Reference側も全画素予測は重いので、学習時の中心点と分散を使う簡易Reinhardにする
            
            # Referenceクラスタの統計量 (近似)
            # 学習に使ったサンプルから算出するのが高速
            r_samples = r_flat[idx_r]
            r_labels_samp = kmeans_r.predict(r_samples)
            r_pixels = r_samples[r_labels_samp == r_k]
            
            if len(r_pixels) == 0:
                # 対応する色がない場合は全体平均を使うフォールバック
                r_mean = np.mean(r_lab_full, axis=(0,1))
                r_std = np.std(r_lab_full, axis=(0,1))
            else:
                r_mean = np.mean(r_pixels, axis=0)
                r_std = np.std(r_pixels, axis=0)
            
            t_mean = np.mean(t_pixels, axis=0)
            t_std = np.std(t_pixels, axis=0)
            
            eps = 1e-6
            result_lab[mask] = (t_pixels - t_mean) * (r_std / (t_std + eps)) + r_mean

        return (np.clip(lab2rgb(result_lab), 0, 1) * 255).astype('uint8')


    # --- Main Process ---
    def process(self, target_img: Image.Image, reference_img: Image.Image, 
                intensity: float = 1.0, 
                preserve_luminance: bool = True,
                method: str = "histogram") -> Image.Image:
        
        target_rgb = target_img.convert('RGB')
        ref_rgb = reference_img.convert('RGB')
        
        target_arr = np.array(target_rgb)
        ref_arr = np.array(ref_rgb)
        
        matched_arr = None

        # --- A. Histogram (Dramatic) ---
        if method == "histogram":
            if preserve_luminance:
                t_lab = rgb2lab(target_arr)
                r_lab = rgb2lab(ref_arr)
                matched_lab = t_lab.copy()
                matched_lab[..., 1] = match_histograms(t_lab[..., 1], r_lab[..., 1])
                matched_lab[..., 2] = match_histograms(t_lab[..., 2], r_lab[..., 2])
                matched_arr = (np.clip(lab2rgb(matched_lab), 0, 1) * 255).astype('uint8')
            else:
                matched_arr = match_histograms(target_arr, ref_arr, channel_axis=-1).astype('uint8')

        # --- B. Reinhard (Natural) ---
        elif method == "reinhard":
            if preserve_luminance:
                t_lab = rgb2lab(target_arr)
                full_res = self._apply_reinhard(target_arr, ref_arr)
                r_res_lab = rgb2lab(full_res)
                t_lab[..., 1:] = r_res_lab[..., 1:] # L維持
                matched_arr = (np.clip(lab2rgb(t_lab), 0, 1) * 255).astype('uint8')
            else:
                matched_arr = self._apply_reinhard(target_arr, ref_arr)
        
        # --- C. Covariance 3D (High Quality) ---
        elif method == "covariance":
            if preserve_luminance:
                t_lab = rgb2lab(target_arr)
                full_res = self._apply_covariance(target_arr, ref_arr)
                r_res_lab = rgb2lab(full_res)
                t_lab[..., 1:] = r_res_lab[..., 1:]
                matched_arr = (np.clip(lab2rgb(t_lab), 0, 1) * 255).astype('uint8')
            else:
                matched_arr = self._apply_covariance(target_arr, ref_arr)

        # --- D. Clustering (Segmented) ---
        elif method == "kmeans":
            # K-Meansは構造上、輝度情報を使ってクラスタリングしたほうが精度が良いので
            # preserve_luminance=Trueでも、内部では輝度を使って領域分割する
            full_res = self._apply_kmeans(target_arr, ref_arr, n_clusters=4) # 4分割くらいが丁度いい
            
            if preserve_luminance:
                t_lab = rgb2lab(target_arr)
                r_res_lab = rgb2lab(full_res)
                t_lab[..., 1:] = r_res_lab[..., 1:]
                matched_arr = (np.clip(lab2rgb(t_lab), 0, 1) * 255).astype('uint8')
            else:
                matched_arr = full_res

        else:
            # Fallback
            matched_arr = target_arr

        # 結果をPIL化
        matched_img = Image.fromarray(matched_arr)

        # Intensityブレンド
        if intensity == 1.0:
            return matched_img
        elif intensity == 0.0:
            return target_rgb
        else:
            return Image.blend(target_rgb, matched_img, intensity)

    def apply_to_hald(self, hald_img, reference_img, intensity=1.0, preserve_luminance=True, method="histogram"):
        return self.process(hald_img, reference_img, intensity, preserve_luminance, method)