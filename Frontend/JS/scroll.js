document.addEventListener("DOMContentLoaded", function () {
    const menuLinks = document.querySelectorAll(".menu-link");

    menuLinks.forEach(link => {
        link.addEventListener("click", function (event) {
            event.preventDefault(); // Varsayılan davranışı engelle
            
            const targetId = this.getAttribute("href").substring(1); // Bağlantıdaki hedef ID'yi al
            const targetElement = document.getElementById(targetId); // Hedef elementi seç

            if (targetElement) {
                const offset = document.querySelector(".navbar").offsetHeight; // Sabit navbar yüksekliği
                const targetPosition = targetElement.getBoundingClientRect().top + window.pageYOffset;
                const scrollToPosition = targetPosition - offset; // Hedef pozisyonu navbar yüksekliğine göre ayarla

                window.scrollTo({
                    top: scrollToPosition,
                    behavior: "smooth", // Yumuşak kaydırma
                });
            } else {
                console.error(`Hedef element bulunamadı: ${targetId}`);
            }
        });
    });
});
document.addEventListener("DOMContentLoaded", function () {
    const socialLinks = document.querySelectorAll(".social-icons a");

    socialLinks.forEach(link => {
        link.addEventListener("click", function () {
            link.style.transform = "scale(1.2)";
            setTimeout(() => (link.style.transform = "scale(1)"), 200);
        });
    });
});
