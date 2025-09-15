import streamlit as st
import cv2
import threading
import numpy as np
import time
from datetime import datetime
import queue
import base64
from io import BytesIO
from PIL import Image

# Cấu hình trang
st.set_page_config(
    page_title="Camera Monitoring System",
    page_icon="📹",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main { padding: 0rem 1rem; }
    .camera-container {
        border: 2px solid #333;
        border-radius: 10px;
        padding: 10px;
        margin: 5px;
        background: linear-gradient(135deg, #1e1e1e, #2d2d30);
        position: relative;
    }
    .camera-connected {
        border-color: #00ff00 !important;
        box-shadow: 0 0 10px rgba(0,255,0,0.3);
    }
    .camera-disconnected {
        border-color: #ff0000 !important;
        box-shadow: 0 0 10px rgba(255,0,0,0.3);
    }
    .status-indicator {
        position: absolute;
        top: 10px;
        left: 10px;
        width: 12px;
        height: 12px;
        border-radius: 50%;
        z-index: 100;
    }
    .status-connected { background-color: #00ff00; }
    .status-disconnected { background-color: #ff0000; }
    .camera-title {
        color: #ffffff;
        font-weight: bold;
        text-align: center;
        margin-bottom: 10px;
        font-size: 14px;
    }
    .stSelectbox > div > div { background-color: #2d2d30; }
    .metric-container {
        background: linear-gradient(135deg, #1e3c72, #2a5298);
        padding: 15px;
        border-radius: 10px;
        margin: 5px;
    }
    
    /* Custom styles for dialog/popup */
    [data-testid="stDialog"] {
        background: linear-gradient(135deg, #1e1e1e, #2d2d30) !important;
        border: 2px solid #444 !important;
        border-radius: 15px !important;
        box-shadow: 0 10px 30px rgba(0,0,0,0.5) !important;
    }
    
    [data-testid="stDialog"] h1 {
        background: linear-gradient(135deg, #1e3c72, #2a5298) !important;
        color: white !important;
        padding: 15px !important;
        margin: -1rem -1rem 1rem -1rem !important;
        border-radius: 15px 15px 0 0 !important;
        text-align: center !important;
    }
    
    /* Enhance dialog content */
    [data-testid="stDialog"] .stMarkdown {
        color: #ffffff !important;
    }
    
    [data-testid="stDialog"] .stImage > div {
        border: 2px solid #444 !important;
        border-radius: 10px !important;
        overflow: hidden !important;
    }
</style>
""", unsafe_allow_html=True)

class CameraManager:
    def __init__(self):
        self.cameras = {}
        self.frames = {}
        self.status = {}
        self.threads = {}
        self.running = {}
        self.frame_queues = {}
        
    def read_camera_urls(self, filename):
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                urls = [line.strip() for line in f if line.strip()]
            return urls
        except FileNotFoundError:
            # Mock URLs nếu file không tồn tại
            return [
                f"rtsp://camera{i+1}.example.com/stream" 
                for i in range(16)
            ]
    
    def camera_thread(self, idx, url):
        cap = cv2.VideoCapture(url)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Giảm buffer để real-time hơn
        
        # Tạo mock frame nếu không kết nối được
        mock_frame = self.create_mock_frame(f"Camera {idx+1}")
        
        while self.running.get(idx, False):
            ret, frame = cap.read()
            
            if ret:
                self.status[idx] = "connected"
                # Không resize, giữ nguyên kích thước gốc để giữ nét chữ và hình ảnh
                self.frames[idx] = frame
            else:
                self.status[idx] = "disconnected" 
                self.frames[idx] = mock_frame
                
            # Thêm timestamp lên frame
            if idx in self.frames:
                self.add_timestamp_to_frame(idx)
            
            time.sleep(0.033)  # ~30 FPS
            
        cap.release()
    
    def create_mock_frame(self, camera_name):
        # Tạo frame giả với gradient và text
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        
        # Tạo gradient background
        for i in range(240):
            intensity = int(30 + (i / 240) * 50)
            frame[i, :] = [intensity, intensity//2, intensity//3]
        
        # Thêm text camera name
        font = cv2.FONT_HERSHEY_SIMPLEX
        text_size = cv2.getTextSize(camera_name, font, 0.7, 2)[0]
        text_x = (320 - text_size[0]) // 2
        text_y = (240 + text_size[1]) // 2
        
        cv2.putText(frame, camera_name, (text_x, text_y), 
                   font, 0.7, (255, 255, 255), 2)
        
        # Thêm "NO SIGNAL" text
        no_signal_size = cv2.getTextSize("NO SIGNAL", font, 0.5, 1)[0]
        no_signal_x = (320 - no_signal_size[0]) // 2
        no_signal_y = text_y + 30
        
        cv2.putText(frame, "NO SIGNAL", (no_signal_x, no_signal_y), 
                   font, 0.5, (0, 0, 255), 1)
        
        return frame
    
    def add_timestamp_to_frame(self, idx):
        if idx in self.frames and self.frames[idx] is not None:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cv2.putText(self.frames[idx], timestamp, (5, 230), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)
            
            # Thêm recording indicator
            if self.status.get(idx) == "connected":
                cv2.circle(self.frames[idx], (300, 20), 5, (0, 0, 255), -1)
                cv2.putText(self.frames[idx], "REC", (270, 25), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.3, (0, 0, 255), 1)
    
    def start_camera(self, idx, url):
        if idx not in self.running or not self.running[idx]:
            self.running[idx] = True
            self.threads[idx] = threading.Thread(
                target=self.camera_thread, 
                args=(idx, url), 
                daemon=True
            )
            self.threads[idx].start()
    
    def stop_camera(self, idx):
        self.running[idx] = False
        if idx in self.threads:
            self.threads[idx].join(timeout=1)
    
    def stop_all_cameras(self):
        for idx in list(self.running.keys()):
            self.stop_camera(idx)
    
    def frame_to_base64(self, frame):
        if frame is None:
            return None
        import base64
        _, buffer = cv2.imencode('.png', frame)
        img_base64 = base64.b64encode(buffer).decode()
        return f"data:image/png;base64,{img_base64}"

# Initialize camera manager
if 'camera_manager' not in st.session_state:
    st.session_state.camera_manager = CameraManager()
    st.session_state.cameras_started = False

def main():
    st.title("🎥 Camera Monitoring System")
    st.markdown("---")
    
    # Sidebar controls
    with st.sidebar:
        st.header("⚙️ Controls")
        
        # Load camera URLs
        uploaded_file = st.file_uploader(
            "Upload camera config file", 
            type=['txt'],
            help="Upload a text file with RTSP URLs, one per line"
        )
        
        if uploaded_file:
            camera_urls = uploaded_file.read().decode().strip().split('\n')
            camera_urls = [url.strip() for url in camera_urls if url.strip()]
        else:
            camera_urls = st.session_state.camera_manager.read_camera_urls('txt/mbf.txt')
        
        st.write(f"📡 **Total Cameras:** {len(camera_urls)}")
        
        # View mode selector
        view_modes = {
            "2x2 Grid": {"cols": 2, "cameras_per_page": 4},
            "3x3 Grid": {"cols": 3, "cameras_per_page": 9}, 
            "4x4 Grid": {"cols": 4, "cameras_per_page": 16},
            "6x6 Grid": {"cols": 6, "cameras_per_page": 36}
        }
        
        selected_view = st.selectbox(
            "🔲 View Mode", 
            list(view_modes.keys()),
            index=1  # Default to 3x3
        )
        
        view_config = view_modes[selected_view]
        cameras_per_page = view_config["cameras_per_page"]
        total_pages = (len(camera_urls) - 1) // cameras_per_page + 1
        
        # Pagination
        if total_pages > 1:
            current_page = st.selectbox(
                "📄 Page", 
                range(1, total_pages + 1),
                format_func=lambda x: f"Page {x} of {total_pages}"
            ) - 1
        else:
            current_page = 0
        
        st.markdown("---")
        
        # System controls
        col1, col2 = st.columns(2)
        with col1:
            if st.button("▶️ Start All", use_container_width=True):
                for idx, url in enumerate(camera_urls):
                    st.session_state.camera_manager.start_camera(idx, url)
                st.session_state.cameras_started = True
                st.rerun()
        
        with col2:
            if st.button("⏹️ Stop All", use_container_width=True):
                st.session_state.camera_manager.stop_all_cameras()
                st.session_state.cameras_started = False
                st.rerun()
        
        # Auto refresh
        auto_refresh = st.checkbox("🔄 Auto Refresh", value=True)
        if auto_refresh:
            refresh_rate = st.slider("Refresh Rate (seconds)", 0.5, 5.0, 1.0, 0.5)
        
        st.markdown("---")
        
        # Statistics
        if st.session_state.cameras_started:
            connected = sum(1 for status in st.session_state.camera_manager.status.values() 
                          if status == "connected")
            disconnected = len(camera_urls) - connected
            
            st.markdown("### 📊 Status")
            st.success(f"✅ Connected: {connected}")
            st.error(f"❌ Disconnected: {disconnected}")
            
            # Performance metrics
            st.markdown("### ⚡ Performance")
            st.info(f"🖼️ Total Frames: {len(st.session_state.camera_manager.frames)}")
            st.info(f"🧵 Active Threads: {len([t for t in st.session_state.camera_manager.threads.values() if t.is_alive()])}")

    # Main content area
    if not st.session_state.cameras_started:
        st.info("👆 Click 'Start All' in the sidebar to begin monitoring cameras")
        return
    
    # Calculate cameras for current page
    start_idx = current_page * cameras_per_page
    end_idx = min(start_idx + cameras_per_page, len(camera_urls))
    current_cameras = camera_urls[start_idx:end_idx]
    
    # Page info
    st.write(f"**Page {current_page + 1} of {total_pages}** - Showing cameras {start_idx + 1} to {end_idx}")
    
    # Create camera grid
    cols = view_config["cols"]
    
    # Calculate number of rows needed
    rows_needed = (len(current_cameras) + cols - 1) // cols
    
    for row in range(rows_needed):
        columns = st.columns(cols)
        
        for col_idx in range(cols):
            camera_idx = row * cols + col_idx
            global_camera_idx = start_idx + camera_idx
            
            if camera_idx < len(current_cameras):
                url = current_cameras[camera_idx]
                camera_name = f"Camera {global_camera_idx + 1}"
                
                with columns[col_idx]:
                    # Camera container
                    status = st.session_state.camera_manager.status.get(global_camera_idx, "disconnected")
                    status_class = "camera-connected" if status == "connected" else "camera-disconnected"
                    
                    # Camera title and status
                    col_title, col_status = st.columns([3, 1])
                    with col_title:
                        st.markdown(f"**{camera_name}**")
                    with col_status:
                        if status == "connected":
                            st.markdown("🟢")
                        else:
                            st.markdown("🔴")
                    
                    # Display camera feed
                    frame = st.session_state.camera_manager.frames.get(global_camera_idx)
                    
                    if frame is not None:
                        # Convert frame to base64 for display
                        img_base64 = st.session_state.camera_manager.frame_to_base64(frame)
                        if img_base64:
                            st.image(img_base64, use_container_width=True)
                    else:
                        st.image("data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMzIwIiBoZWlnaHQ9IjI0MCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48cmVjdCB3aWR0aD0iMTAwJSIgaGVpZ2h0PSIxMDAlIiBmaWxsPSIjMzMzIi8+PHRleHQgeD0iNTAlIiB5PSI1MCUiIGZvbnQtZmFtaWx5PSJBcmlhbCIgZm9udC1zaXplPSIxNCIgZmlsbD0iI2ZmZiIgdGV4dC1hbmNob3I9Im1pZGRsZSIgZHk9Ii4zZW0iPk5vIFNpZ25hbDwvdGV4dD48L3N2Zz4=", 
                               use_container_width=True)
                    
                    # Camera controls
                    col_btn1, col_btn2, col_btn3 = st.columns(3)
                    with col_btn1:
                        if st.button("👁️", key=f"view_{global_camera_idx}", help="View Details"):
                            st.session_state.show_camera_details = True
                            st.session_state.selected_camera = global_camera_idx
                    with col_btn2:
                        if st.button("⚙️", key=f"settings_{global_camera_idx}", help="Settings"):
                            st.info(f"Settings for {camera_name}")
                    with col_btn3:
                        if st.button("🔄", key=f"refresh_{global_camera_idx}", help="Refresh"):
                            st.session_state.camera_manager.stop_camera(global_camera_idx)
                            st.session_state.camera_manager.start_camera(global_camera_idx, url)
            else:
                # Empty column for grid alignment
                with columns[col_idx]:
                    st.empty()
    
    # Camera details popup dialog
    if st.session_state.get('show_camera_details', False) and 'selected_camera' in st.session_state:
        selected_idx = st.session_state.selected_camera
        
        @st.dialog(f"🔍 Camera {selected_idx + 1} Details")
        def show_camera_details():
            # Check if dialog should be closed (escape key or clicking outside)
            if not st.session_state.get('show_camera_details', False):
                return
                
            # Camera information
            st.markdown("### 📊 Camera Information")
            col1, col2 = st.columns(2)
            
            with col1:
                status = st.session_state.camera_manager.status.get(selected_idx, "disconnected")
                if status == "connected":
                    st.success("✅ Status: Connected")
                else:
                    st.error("❌ Status: Disconnected")
                
                st.info("📐 Resolution: 320x240")
                st.info("🎬 FPS: ~30")
            
            with col2:
                st.info("🎥 Codec: H.264")
                camera_url = camera_urls[selected_idx] if selected_idx < len(camera_urls) else "Unknown"
                st.info(f"🔗 URL: {camera_url[:30]}..." if len(camera_url) > 30 else f"🔗 URL: {camera_url}")
                
                # Timestamp của frame hiện tại
                current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                st.info(f"🕒 Last Update: {current_time}")
            
            st.markdown("---")
            
            # Large view of selected camera
            st.markdown("### 🖼️ Live Preview")
            frame = st.session_state.camera_manager.frames.get(selected_idx)
            
            if frame is not None:
                # Hiển thị frame với kích thước lớn hơn
                img_base64 = st.session_state.camera_manager.frame_to_base64(frame)
                if img_base64:
                    st.image(img_base64, 
                           caption=f"Camera {selected_idx + 1} - Live Feed", 
                           use_container_width=True)
            else:
                st.warning("🚫 No video signal available")
                st.image("data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iNjQwIiBoZWlnaHQ9IjQ4MCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48cmVjdCB3aWR0aD0iMTAwJSIgaGVpZ2h0PSIxMDAlIiBmaWxsPSIjMzMzIi8+PHRleHQgeD0iNTAlIiB5PSI0NSUiIGZvbnQtZmFtaWx5PSJBcmlhbCIgZm9udC1zaXplPSIyNCIgZmlsbD0iI2ZmZiIgdGV4dC1hbmNob3I9Im1pZGRsZSI+Tm8gU2lnbmFsPC90ZXh0Pjx0ZXh0IHg9IjUwJSIgeT0iNTUlIiBmb250LWZhbWlseT0iQXJpYWwiIGZvbnQtc2l6ZT0iMTYiIGZpbGw9IiNhYWEiIHRleHQtYW5jaG9yPSJtaWRkbGUiPkNhbWVyYSBEaXNjb25uZWN0ZWQ8L3RleHQ+PC9zdmc+", 
                       use_container_width=True)
            
            st.markdown("---")
            
            # Action buttons
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                if st.button("🔄 Refresh Camera", use_container_width=True):
                    st.session_state.camera_manager.stop_camera(selected_idx)
                    camera_url = camera_urls[selected_idx] if selected_idx < len(camera_urls) else ""
                    if camera_url:
                        st.session_state.camera_manager.start_camera(selected_idx, camera_url)
                    st.success("Camera refreshed!")
            
            with col2:
                if st.button("⚙️ Settings", use_container_width=True):
                    st.info("Settings panel coming soon...")
            
            with col3:
                if st.button("📱 Fullscreen", use_container_width=True):
                    st.info("Fullscreen mode coming soon...")
                    
            with col4:
                if st.button("❌ Close", use_container_width=True, type="primary"):
                    # Clear all popup related states
                    st.session_state.show_camera_details = False
                    if 'selected_camera' in st.session_state:
                        del st.session_state.selected_camera
                    # Force rerun to close dialog
                    st.rerun()
            
            # Alternative close method - show instruction
            st.markdown("---")
            st.markdown("💡 **Tip:** Press `ESC` or click outside to close this dialog")
        
        show_camera_details()
        
        # Check if dialog was closed externally (ESC or click outside)
        # If the dialog function completes without explicit close, clean up
        if st.session_state.get('show_camera_details', False):
            # Dialog was closed externally, clean up state
            st.session_state.show_camera_details = False
            if 'selected_camera' in st.session_state:
                del st.session_state.selected_camera
    
    # Status bar
    st.markdown("---")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown(f"**🕒 Last Update:** {datetime.now().strftime('%H:%M:%S')}")
    
    with col2:
        if st.session_state.cameras_started:
            connected_count = sum(1 for status in st.session_state.camera_manager.status.values() 
                                if status == "connected")
            st.markdown(f"**📊 Connected:** {connected_count}/{len(camera_urls)}")
    
    with col3:
        if st.button("🔄 Refresh Now"):
            st.rerun()
    
    # Auto refresh (only when popup is not open)
    if auto_refresh and st.session_state.cameras_started and not st.session_state.get('show_camera_details', False):
        time.sleep(refresh_rate)
        st.rerun()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        st.session_state.camera_manager.stop_all_cameras()
        st.write("Camera monitoring stopped.")