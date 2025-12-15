import streamlit as st
from PIL import Image
import io
import base64

# 比較用スライダーライブラリ
from streamlit_image_comparison import image_comparison

# 内部モジュール
from core.image_processor import ColorGradingEngine
from core.lut_converter import LutGenerator

st.set_page_config(layout="wide", page_title="Cinematic Color Stealer")

# --- Helper Functions ---

def init_session_state():
    """
    セッション状態（変数の箱）を確実に初期化する関数
    main()の最初で必ず呼び出す
    """
    # モード設定
    if 'swap_mode' not in st.session_state: 
        st.session_state.swap_mode = False
    
    # 画像データ
    if 'img_left' not in st.session_state: 
        st.session_state.img_left = None
    if 'img_right' not in st.session_state: 
        st.session_state.img_right = None

    # アップローダーの管理キー
    if 'key_left_idx' not in st.session_state: 
        st.session_state.key_left_idx = 0
    if 'key_right_idx' not in st.session_state: 
        st.session_state.key_right_idx = 0
        
    # メソッド選択
    if 'grading_method' not in st.session_state:
        st.session_state.grading_method = "histogram"

def image_to_base64_str(img, quality=80):
    """HTML表示用にPIL画像をBase64文字列に変換する"""
    if img is None: return ""
    
    img_copy = img.copy()
    if img_copy.mode in ('RGBA', 'LA'):
        bg = Image.new("RGB", img_copy.size, (255,255,255))
        bg.paste(img_copy, mask=img_copy.split()[-1])
        img_copy = bg
    else:
        img_copy = img_copy.convert('RGB')
    
    img_copy.thumbnail((1000, 1000))
    
    buffered = io.BytesIO()
    img_copy.save(buffered, format="JPEG", quality=quality)
    return f"data:image/jpeg;base64,{base64.b64encode(buffered.getvalue()).decode()}"

def render_preview_area(image, title, key):
    """
    プレビューエリアとアップローダーを描画するコンポーネント
    """
    st.markdown(f"### {title}")
    
    with st.container(border=True):
        if image:
            b64_img = image_to_base64_str(image)
            st.markdown(
                f"""
                <div style="width: 100%; margin-bottom: 10px;">
                    <img src="{b64_img}" style="width: 100%; border-radius: 5px; object-fit: contain;">
                </div>
                """,
                unsafe_allow_html=True
            )
            status_text = "✅ Image Loaded (Change?)"
        else:
            st.markdown(
                """
                <div style='
                    height: 200px; 
                    display: flex; 
                    align-items: center; 
                    justify-content: center; 
                    background-color: #262730; 
                    color: #aaa; 
                    border: 2px dashed #444; 
                    border-radius: 10px;
                    margin-bottom: 10px;
                '>
                    <div style='text-align: center;'>
                        <span style='font-size: 30px;'>⬇️</span><br>
                        Drag & Drop Image Below
                    </div>
                </div>
                """,
                unsafe_allow_html=True
            )
            status_text = "Upload Image"

        uploaded_file = st.file_uploader(
            label=status_text,
            type=["jpg", "png", "jpeg"],
            key=key,
            label_visibility="collapsed"
        )
        
        return uploaded_file

def main():
    st.title("🎬 Cinematic Color Stealer")

    # ★ここで必ず初期化を実行する
    init_session_state()

    grader = ColorGradingEngine()
    lut_gen = LutGenerator()

    # Role Swap
    with st.container():
        if st.button("🔄 Swap Roles (役割を入れ替え)"):
            st.session_state.swap_mode = not st.session_state.swap_mode

    col1, col2 = st.columns(2)

    label_left = "📂 Target Image (変えたい画像)" if not st.session_state.swap_mode else "🎨 Reference Image (憧れの色味)"
    label_right = "🎨 Reference Image (憧れの色味)" if not st.session_state.swap_mode else "📂 Target Image (変えたい画像)"

    # --- Upload Area ---
    with col1:
        uploaded_left = render_preview_area(
            st.session_state.img_left, 
            label_left, 
            f"u_left_{st.session_state.key_left_idx}"
        )
        if uploaded_left:
            st.session_state.img_left = Image.open(uploaded_left).convert('RGB')
            st.session_state.key_left_idx += 1
            st.rerun()

    with col2:
        uploaded_right = render_preview_area(
            st.session_state.img_right, 
            label_right, 
            f"u_right_{st.session_state.key_right_idx}"
        )
        if uploaded_right:
            st.session_state.img_right = Image.open(uploaded_right).convert('RGB')
            st.session_state.key_right_idx += 1
            st.rerun()

    # --- Logic ---
    target_img = None
    ref_img = None

    # 画像が揃っているか確認
    if st.session_state.img_left and st.session_state.img_right:
        if st.session_state.swap_mode:
            target_img = st.session_state.img_right
            ref_img = st.session_state.img_left
        else:
            target_img = st.session_state.img_left
            ref_img = st.session_state.img_right

        st.divider()

        # --- Settings Area ---
        st.subheader("⚙️ Grading Settings")
        
        s_col1, s_col2 = st.columns(2)
        
        with s_col1:
            method_choice = st.radio(
                "Algorithm Mode",
                ("Histogram Match (Dramatic)", "Reinhard (Natural)"),
                help="Histogram: 色の分布を強制的に合わせます。\nReinhard: 全体の平均的な色味だけを合わせます。"
            )
            st.session_state.grading_method = "histogram" if "Histogram" in method_choice else "reinhard"

        with s_col2:
            preserve_lum = st.checkbox("💡 Preserve Luminance (明るさ維持)", value=True)

        # Generate Button
        if st.button("🚀 Generate Cinematic Look", type="primary", use_container_width=True):
            with st.spinner("Analyzing & Stealing colors..."):
                full_effect_img = grader.process(
                    target_img, 
                    ref_img, 
                    intensity=1.0, 
                    preserve_luminance=preserve_lum,
                    method=st.session_state.grading_method
                )
                
                st.session_state.result_full = full_effect_img
                st.session_state.result_target = target_img
                st.session_state.result_ref = ref_img
                st.session_state.preserve_setting = preserve_lum

    # --- Result View ---
    if 'result_full' in st.session_state:
        st.subheader("Adjust & Preview")
        
        # 1. 統合スライダー
        final_intensity = st.slider("Effect Intensity (適用の強さ)", 0.0, 1.0, 0.8, 0.05)
        
        # 2. ブレンド処理
        blended_img = Image.blend(
            st.session_state.result_target, 
            st.session_state.result_full, 
            final_intensity
        )

        # 3. 比較表示
        display_w = 800
        w_p = (display_w / float(st.session_state.result_target.size[0]))
        h_s = int((float(st.session_state.result_target.size[1]) * float(w_p)))
        
        comp_original = st.session_state.result_target.resize((display_w, h_s))
        comp_result = blended_img.resize((display_w, h_s))
        
        image_comparison(
            img1=comp_original,
            img2=comp_result,
            label1="Original",
            label2=f"Cinematic ({int(final_intensity*100)}%)",
            width=display_w
        )

        st.divider()
        
        # --- Download Section ---
        st.subheader("Download Result")
        st.caption("※上のスライダーで調整した結果がダウンロードされます")

        d_col1, d_col2 = st.columns(2)
        
        with d_col1:
            buf = io.BytesIO()
            blended_img.save(buf, format="PNG")
            
            st.download_button(
                label="画像をダウンロード (PNG)",
                data=buf.getvalue(),
                file_name="cinematic_result.png",
                mime="image/png",
                use_container_width=True
            )

        with d_col2:
            if st.button("LUTを生成 (.cube)"):
                with st.spinner("Generating LUT..."):
                    identity_hald = lut_gen.generate_simple_identity_hald_8()
                    
                    processed_hald = grader.apply_to_hald(
                        identity_hald, 
                        st.session_state.result_ref, 
                        intensity=final_intensity,
                        preserve_luminance=st.session_state.preserve_setting,
                        method=st.session_state.grading_method
                    )
                    cube_data = lut_gen.convert_to_cube(processed_hald, title="Cinematic")
                    
                    st.download_button(
                        label="Download Ready! (.cube)",
                        data=cube_data,
                        file_name="cinematic.cube",
                        mime="text/plain",
                        use_container_width=True
                    )

if __name__ == "__main__":
    main()