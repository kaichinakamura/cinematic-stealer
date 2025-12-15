import streamlit as st
from PIL import Image
import io
import base64
import zipfile
import datetime
# 固有ID生成用のライブラリを追加
import uuid

from streamlit_image_comparison import image_comparison
from core.image_processor import ColorGradingEngine
from core.lut_converter import LutGenerator

st.set_page_config(layout="wide", page_title="Cinematic Color Stealer")

# --- Helper Functions ---

def init_session_state():
    if 'swap_mode' not in st.session_state: st.session_state.swap_mode = False
    if 'img_left' not in st.session_state: st.session_state.img_left = None
    if 'img_right' not in st.session_state: st.session_state.img_right = None
    if 'key_left_idx' not in st.session_state: st.session_state.key_left_idx = 0
    if 'key_right_idx' not in st.session_state: st.session_state.key_right_idx = 0
    if 'grading_method' not in st.session_state: st.session_state.grading_method = "histogram"
    if 'snapshots' not in st.session_state: st.session_state.snapshots = []

def image_to_base64_str(img, quality=80):
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
    st.markdown(f"### {title}")
    with st.container(border=True):
        if image:
            b64_img = image_to_base64_str(image)
            st.markdown(
                f"""<div style="width: 100%; margin-bottom: 10px;">
                    <img src="{b64_img}" style="width: 100%; border-radius: 5px; object-fit: contain;">
                </div>""",
                unsafe_allow_html=True
            )
            status_text = "✅ Image Loaded"
        else:
            st.markdown(
                """<div style='height: 200px; display: flex; align-items: center; justify-content: center; background-color: #262730; color: #aaa; border: 2px dashed #444; border-radius: 10px; margin-bottom: 10px;'>
                    <div style='text-align: center;'><span style='font-size: 30px;'>⬇️</span><br>Drag & Drop Image Below</div>
                </div>""",
                unsafe_allow_html=True
            )
            status_text = "Upload Image"

        uploaded_file = st.file_uploader(label=status_text, type=["jpg", "png", "jpeg"], key=key, label_visibility="collapsed")
        return uploaded_file

def create_zip_from_snapshots(snapshots):
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for i, snap in enumerate(snapshots):
            prefix = f"{i+1:02d}_{snap['method']}_{int(snap['intensity']*100)}pct"
            
            img_buffer = io.BytesIO()
            snap['image'].save(img_buffer, format="PNG")
            zip_file.writestr(f"{prefix}_result.png", img_buffer.getvalue())
            
            if snap['lut_data']:
                zip_file.writestr(f"{prefix}.cube", snap['lut_data'])
                
            info_txt = f"Method: {snap['method']}\nIntensity: {snap['intensity']}\nPreserve Luminance: {snap['preserve_lum']}\nCreated: {snap['created_at']}\nID: {snap['id']}"
            zip_file.writestr(f"{prefix}_info.txt", info_txt)
    return zip_buffer.getvalue()

def main():
    st.title("🎬 Cinematic Color Stealer")
    init_session_state()

    grader = ColorGradingEngine()
    lut_gen = LutGenerator()

    with st.container():
        if st.button("🔄 Swap Roles (役割を入れ替え)"):
            st.session_state.swap_mode = not st.session_state.swap_mode

    col1, col2 = st.columns(2)
    label_left = "📂 Target Image (変えたい画像)" if not st.session_state.swap_mode else "🎨 Reference Image (憧れの色味)"
    label_right = "🎨 Reference Image (憧れの色味)" if not st.session_state.swap_mode else "📂 Target Image (変えたい画像)"

    with col1:
        uploaded_left = render_preview_area(st.session_state.img_left, label_left, f"u_left_{st.session_state.key_left_idx}")
        if uploaded_left:
            st.session_state.img_left = Image.open(uploaded_left).convert('RGB')
            st.session_state.key_left_idx += 1
            st.rerun()

    with col2:
        uploaded_right = render_preview_area(st.session_state.img_right, label_right, f"u_right_{st.session_state.key_right_idx}")
        if uploaded_right:
            st.session_state.img_right = Image.open(uploaded_right).convert('RGB')
            st.session_state.key_right_idx += 1
            st.rerun()

    target_img = None
    ref_img = None
    if st.session_state.img_left and st.session_state.img_right:
        if st.session_state.swap_mode:
            target_img = st.session_state.img_right
            ref_img = st.session_state.img_left
        else:
            target_img = st.session_state.img_left
            ref_img = st.session_state.img_right

        st.divider()

        # Settings
        st.subheader("⚙️ Grading Settings")
        s_col1, s_col2 = st.columns(2)
        with s_col1:
            method_display = st.radio(
                "Algorithm Mode",
                (
                    "Histogram Match (Dramatic)", 
                    "Reinhard (Natural)", 
                    "Covariance 3D (Rich)", 
                    "Clustering AI (Segmented)"
                ),
                help="""
                - Histogram: 色の分布を強制一致。劇的だがノイズが出やすい。
                - Reinhard: 平均的な色味をコピー。自然で滑らか。
                - Covariance 3D: 色の相関関係もコピー。Reinhardよりリッチ。
                - Clustering AI: 画像を領域分割して個別に色合わせ。部分的な色移りに強い。
                """
            )
            
            # 表示名から内部キーへの変換マップ
            key_map = {
                "Histogram Match (Dramatic)": "histogram",
                "Reinhard (Natural)": "reinhard",
                "Covariance 3D (Rich)": "covariance",
                "Clustering AI (Segmented)": "kmeans"
            }
            st.session_state.grading_method = key_map[method_display]
        with s_col2:
            preserve_lum = st.checkbox("💡 Preserve Luminance (明るさ維持)", value=True)

        if st.button("🚀 Generate Cinematic Look", type="primary", use_container_width=True):
            with st.spinner("Analyzing colors..."):
                full_effect_img = grader.process(
                    target_img, ref_img, intensity=1.0, 
                    preserve_luminance=preserve_lum, method=st.session_state.grading_method
                )
                st.session_state.result_full = full_effect_img
                st.session_state.result_target = target_img
                st.session_state.result_ref = ref_img
                st.session_state.preserve_setting = preserve_lum

    if 'result_full' in st.session_state:
        st.subheader("Adjust & Preview")
        
        final_intensity = st.slider("Effect Intensity", 0.0, 1.0, 0.8, 0.05)
        blended_img = Image.blend(st.session_state.result_target, st.session_state.result_full, final_intensity)

        display_w = 800
        w_p = (display_w / float(st.session_state.result_target.size[0]))
        h_s = int((float(st.session_state.result_target.size[1]) * float(w_p)))
        comp_original = st.session_state.result_target.resize((display_w, h_s))
        comp_result = blended_img.resize((display_w, h_s))
        
        image_comparison(
            img1=comp_original, img2=comp_result,
            label1="Original", label2=f"Result ({int(final_intensity*100)}%)",
            width=display_w
        )

        st.divider()

        c1, c2, c3 = st.columns([1, 2, 1])
        with c2:
            if st.button("📸 Keep this Look (Save to List)", type="primary", use_container_width=True):
                identity_hald = lut_gen.generate_simple_identity_hald_8()
                processed_hald = grader.apply_to_hald(
                    identity_hald, 
                    st.session_state.result_ref, 
                    intensity=final_intensity,
                    preserve_luminance=st.session_state.preserve_setting,
                    method=st.session_state.grading_method
                )
                lut_data = lut_gen.convert_to_cube(processed_hald, title="Cinematic")

                # 【重要】UUIDを使って固有IDを生成する
                snap_id = str(uuid.uuid4())

                new_snap = {
                    "id": snap_id,  # これをKeyの種にする
                    "image": blended_img,
                    "lut_data": lut_data,
                    "method": st.session_state.grading_method,
                    "intensity": final_intensity,
                    "preserve_lum": st.session_state.preserve_setting,
                    "created_at": datetime.datetime.now().strftime("%H:%M:%S")
                }
                st.session_state.snapshots.append(new_snap)
                st.success("Saved to Snapshots below! ⬇️")

    # --- Snapshot Gallery ---
    if st.session_state.snapshots:
        st.divider()
        st.subheader(f"🖼️ Snapshots ({len(st.session_state.snapshots)})")
        
        if len(st.session_state.snapshots) > 0:
            zip_bytes = create_zip_from_snapshots(st.session_state.snapshots)
            st.download_button(
                label="📦 Download All Snapshots (ZIP)",
                data=zip_bytes,
                file_name="cinematic_snapshots.zip",
                mime="application/zip",
                type="primary"
            )

        st.caption("気に入った結果をここからダウンロードしてください。")
        
        # ギャラリー表示 (逆順)
        # enumerateのインデックスはあくまで表示用番号として使い、
        # コンポーネントのKeyには「snap['id']」という不変のIDを使うことでバグを防ぐ
        for i, snap in enumerate(reversed(st.session_state.snapshots)):
            display_num = len(st.session_state.snapshots) - i
            unique_key = snap['id'] # UUIDを使用
            
            with st.expander(f"Snapshot #{display_num} | {snap['method']} ({int(snap['intensity']*100)}%)", expanded=True):
                cols = st.columns([1, 2])
                with cols[0]:
                    st.image(snap['image'], use_container_width=True)
                with cols[1]:
                    st.markdown(f"""
                    - **Method:** {snap['method']}
                    - **Intensity:** {snap['intensity']}
                    - **Preserve Luminance:** {snap['preserve_lum']}
                    - **Time:** {snap['created_at']}
                    """)
                    
                    b_col1, b_col2 = st.columns(2)
                    with b_col1:
                        buf = io.BytesIO()
                        snap['image'].save(buf, format="PNG")
                        st.download_button(
                            f"Download IMG", 
                            buf.getvalue(), 
                            f"snap_{display_num}.png", 
                            "image/png", 
                            key=f"dl_img_{unique_key}" # KeyをUUIDベースに変更
                        )
                    with b_col2:
                        st.download_button(
                            f"Download LUT", 
                            snap['lut_data'], 
                            f"snap_{display_num}.cube", 
                            "text/plain", 
                            key=f"dl_lut_{unique_key}" # KeyをUUIDベースに変更
                        )
                    
                    # 削除ボタン
                    if st.button("🗑️ Delete", key=f"del_{unique_key}"): # KeyをUUIDベースに変更
                        # IDで一致するものをリストから除外して再構築する
                        st.session_state.snapshots = [s for s in st.session_state.snapshots if s['id'] != unique_key]
                        st.rerun()

if __name__ == "__main__":
    main()