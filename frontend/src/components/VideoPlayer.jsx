import { useRef, useEffect, forwardRef, useImperativeHandle } from 'react';

const VideoPlayer = forwardRef(({ src, seekTime }, ref) => {
  const videoRef = useRef(null);

  useImperativeHandle(ref, () => ({
    getCurrentTime: () => videoRef.current?.currentTime || 0,
    seek: (time) => {
      if (videoRef.current) videoRef.current.currentTime = time;
    },
  }));

  useEffect(() => {
    if (seekTime !== null && seekTime !== undefined && videoRef.current) {
      videoRef.current.currentTime = seekTime;
    }
  }, [seekTime]);

  if (!src) {
    return (
      <div className="flex-1 flex items-center justify-center bg-black/50 text-gray-500">
        <p>Upload a video to get started</p>
      </div>
    );
  }

  return (
    <div className="flex-1 flex items-center justify-center bg-black">
      <video
        ref={videoRef}
        src={src}
        controls
        className="w-full h-full object-contain"
      />
    </div>
  );
});

VideoPlayer.displayName = 'VideoPlayer';
export default VideoPlayer;
