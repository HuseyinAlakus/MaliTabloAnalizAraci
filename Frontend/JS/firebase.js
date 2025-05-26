// Firebase SDK modüllerini içe aktar
import { initializeApp } from "https://www.gstatic.com/firebasejs/10.0.0/firebase-app.js";
import { getAuth, createUserWithEmailAndPassword, signInWithEmailAndPassword, signOut, onAuthStateChanged } from "https://www.gstatic.com/firebasejs/10.0.0/firebase-auth.js";
import { getFirestore, doc, setDoc, getDoc } from "https://www.gstatic.com/firebasejs/10.0.0/firebase-firestore.js";

// Firebase konfigürasyonu (Senin bilgilerle güncellendi)
const firebaseConfig = {
    apiKey: "AIzaSyB0D2xvMPu_zCz0eJkRS0YoiWXcMKaE3Lw",
    authDomain: "mali-tablo-analiz-araci.firebaseapp.com",
    projectId: "mali-tablo-analiz-araci",
    storageBucket: "mali-tablo-analiz-araci.firebasestorage.app",
    messagingSenderId: "276225207436",
    appId: "1:276225207436:web:07ad4d3cc08d0af8415fa9",
    measurementId: "G-83L756WGJL"
};

// Firebase başlat
const app = initializeApp(firebaseConfig);
const auth = getAuth(app);
const db = getFirestore(app);

export { auth, db };

// **Kullanıcı Kayıt Fonksiyonu**
export async function registerUser(isim, soyisim, email, password) {
    try {
        const userCredential = await createUserWithEmailAndPassword(auth, email, password);
        const user = userCredential.user;

        // Firestore'a kullanıcı bilgilerini kaydet
        await setDoc(doc(db, "users", user.uid), {
            isim: isim,
            soyisim: soyisim,
            email: email,
            uid: user.uid
        });

        alert("Kayıt başarılı! Ana sayfaya yönlendiriliyorsunuz...");
        window.location.href = "/AnaSayfa/home.html"; // Kayıt sonrası yönlendirme
    } catch (error) {
        console.error("Hata:", error.message);
        alert(error.message);
    }
}

// **Kullanıcı Giriş Fonksiyonu**
export async function loginUser(email, password) {
    try {
        await signInWithEmailAndPassword(auth, email, password);
        alert("Giriş başarılı! Ana sayfaya yönlendiriliyorsunuz...");
        window.location.href = "/AnaSayfa/home.html"; // Giriş sonrası yönlendirme
    } catch (error) {
        console.error("Hata:", error.message);
        alert(error.message);
    }
}

// **Çıkış Yapma Fonksiyonu**
export async function logoutUser() {
    try {
        await signOut(auth);
        alert("Çıkış yapıldı! Giriş sayfasına yönlendiriliyorsunuz...");
        window.location.href = "/Login/login.html";
    } catch (error) {
        console.error("Hata:", error.message);
        alert(error.message);
    }
}

// **Oturum Kontrolü**
export function checkUser() {
    onAuthStateChanged(auth, async (user) => {
        if (user) {
            // Kullanıcı bilgilerini al ve ekrana yazdır
            const userDoc = await getDoc(doc(db, "users", user.uid));
            if (userDoc.exists()) {
                const userData = userDoc.data();
                document.getElementById("user-info").innerHTML = `<p>Hoş geldiniz, ${userData.isim} ${userData.soyisim}!</p>`;
            }
        } else {
            window.location.href = "/Login/login.html"; // Kullanıcı giriş yapmamışsa yönlendir
        }
    });
}
