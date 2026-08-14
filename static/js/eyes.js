// Eye following cursor animation
document.addEventListener('DOMContentLoaded', function() {
    const pupils = document.querySelectorAll('.pupil');
    
    document.addEventListener('mousemove', function(e) {
        pupils.forEach(pupil => {
            const eye = pupil.parentElement;
            const eyeRect = eye.getBoundingClientRect();
            const eyeCenterX = eyeRect.left + eyeRect.width / 2;
            const eyeCenterY = eyeRect.top + eyeRect.height / 2;
            
            const angle = Math.atan2(e.clientY - eyeCenterY, e.clientX - eyeCenterX);
            const distance = Math.min(8, Math.hypot(e.clientX - eyeCenterX, e.clientY - eyeCenterY) / 30);
            
            const pupilX = Math.cos(angle) * distance;
            const pupilY = Math.sin(angle) * distance;
            
            pupil.style.transform = `translate(calc(-50% + ${pupilX}px), calc(-50% + ${pupilY}px))`;
        });
    });
    
    // Add hover effects to characters
    const characters = document.querySelectorAll('.character');
    characters.forEach(char => {
        char.addEventListener('mouseenter', function() {
            this.style.transform = 'scale(1.05) rotate(2deg)';
        });
        
        char.addEventListener('mouseleave', function() {
            this.style.transform = 'scale(1) rotate(0deg)';
        });
    });
});
