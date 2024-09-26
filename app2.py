import os
import logging
import asyncio
import yt_dlp
import streamlit as st
from moviepy.video.io.ffmpeg_tools import ffmpeg_extract_subclip
from supabase import create_client
from dotenv import load_dotenv
import whisper  # Add whisper import

# Load environment variables from .env file
load_dotenv()

# Replace with your Supabase URL and API key
SUPABASE_URL = "https://hbnageqkqgvpxyftbjvy.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImhibmFnZXFrcWd2cHh5ZnRianZ5Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3MjcyNTM2NzcsImV4cCI6MjA0MjgyOTY3N30._OvBbm96lWN7QMqV3ianCcgmNHjUbMhj0XkZGzduCTM"

# Create Supabase client
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Define output directories
videos_output = 'videos_output'  # Directory for downloaded videos
video_clips_output = 'video_clips'  # Directory for video clips
os.makedirs(videos_output, exist_ok=True)  # Create directory if it doesn't exist
os.makedirs(video_clips_output, exist_ok=True)  # Create clips directory

# yt-dlp options

ydl_opts = {
    'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
    'outtmpl': os.path.join(videos_output, '%(id)s.%(ext)s'),
    'noplaylist': True,
    'cookiefile': 'madd.txt',  # Add this line to specify the cookies file
}

# Load Whisper model
model = whisper.load_model("base")  # Load base model for transcription

async def download_video(url):
    """Download a single video."""
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=True)
            logging.info(f"Downloaded {info['title']} ({info['id']})")
            return os.path.join(videos_output, f"{info['id']}.mp4"), info['id']
        except Exception as e:
            logging.error(f"Error downloading {url}: {str(e)}")
            return None, None

def split_video(video_path):
    """Split the video into three parts."""
    split_times = [(2, 3), (3, 4), (4, 6)]  # (start, end) times in minutes
    part_names = ['first_demo.mp4', 'second_demo.mp4', 'third_demo.mp4']

    for i, (start, end) in enumerate(split_times):
        start_time = start * 60  # Convert to seconds
        end_time = end * 60
        output_path = os.path.join(video_clips_output, part_names[i])
        ffmpeg_extract_subclip(video_path, start_time, end_time, targetname=output_path)
        logging.info(f"Created clip: {output_path}")

def upload_file_to_bucket(bucket_name, file_path):
    """Upload a file to a Supabase bucket and return its URL."""
    filename = os.path.basename(file_path)
    with open(file_path, "rb") as file:
        response = supabase.storage.from_(bucket_name).upload(filename, file)
        if response.status_code == 200:
            logging.info(f"Uploaded {filename} to {bucket_name}.")
            return True  # Return True if upload is successful
        else:
            logging.error(f"Error uploading {filename} to {bucket_name}: {response.error}")
            return False  # Return False if upload fails

def insert_into_database(table_name, data):
    """Insert a record into the specified Supabase table."""
    response = supabase.table(table_name).insert(data).execute()

def transcribe_clip(file_path):
    """Transcribe a video clip using Whisper."""
    logging.info(f"Transcribing clip: {file_path}")
    result = model.transcribe(file_path)  # Run transcription on the clip
    return result['text']

def main():
    st.set_page_config("YouTube Video Downloader")
    st.header("YouTube Video Downloader")

    url_input = st.text_input("Enter YouTube Video URL")

    if st.button("Download, Split and Upload Video"):
        if url_input:
            with st.spinner("Downloading..."):
                video_path, video_id = asyncio.run(download_video(url_input))
                if video_path:
                    st.success(f"Video saved at: {video_path}")
                    with st.spinner("Splitting video..."):
                        split_video(video_path)
                        st.success("Video clips created.")

                        # Upload original video to Supabase
                        with st.spinner("Uploading original video to Supabase..."):
                            if upload_file_to_bucket("videos", video_path):
                                # Construct the URL for the uploaded video
                                video_url = f"https://hbnageqkqgvpxyftbjvy.supabase.co/storage/v1/object/public/videos/{os.path.basename(video_path)}"
                                
                                # Insert original video info into the database
                                video_data = {
                                    "url": video_id,  # Or any identifier you want to use
                                    "storage_url": video_url,
                                }
                                insert_into_database("videos", video_data)

                        # Upload clips to Supabase and transcribe them
                        with st.spinner("Uploading clips to Supabase..."):
                            for clip_filename in os.listdir(video_clips_output):
                                clip_path = os.path.join(video_clips_output, clip_filename)
                                if upload_file_to_bucket("clips", clip_path):
                                    # Construct the URL for the uploaded clip
                                    clip_url = f"https://hbnageqkqgvpxyftbjvy.supabase.co/storage/v1/object/public/clips/{clip_filename}"

                                    # Transcribe the clip
                                    transcript = transcribe_clip(clip_path)
                                    
                                    # Insert clip info into the database
                                    clip_data = {
                                        "storage_url": clip_url,
                                        "original_youtube_url": url_input,
                                        "transcript": transcript,  # Store the transcript
                                    }
                                    insert_into_database("clips", clip_data)

                        st.success("All uploads and transcriptions complete!")

                else:
                    st.error("Error downloading video.")
        else:
            st.warning("Please enter a valid URL.")

if __name__ == "__main__":
    main()
