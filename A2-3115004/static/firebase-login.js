"use strict"

import { initializeApp } from "https://www.gstatic.com/firebasejs/12.9.0/firebase-app.js"
import { getAuth, createUserWithEmailAndPassword, signInWithEmailAndPassword, signOut } from "https://www.gstatic.com/firebasejs/12.9.0/firebase-auth.js"

// REPLACE THIS WITH YOUR ACTUAL FIREBASE CONFIG
const firebaseConfig = {
  apiKey: "AIzaSyAR9U0j-7V--wcoaRrgioQEWS8Xofuhzn0",
  authDomain: "karantwitter-c48fa.firebaseapp.com",
  projectId: "karantwitter-c48fa",
  storageBucket: "karantwitter-c48fa.firebasestorage.app",
  messagingSenderId: "884673318541",
  appId: "1:884673318541:web:60bec06b8df0a9260d5cc4"
};

window.addEventListener("load", function() {
    const app  = initializeApp(firebaseConfig)
    const auth = getAuth()

    updateUI(document.cookie)
    console.log("hello world load")

    document.getElementById("sign-up").addEventListener('click', function() {
        const email    = document.getElementById("email").value
        const password = document.getElementById("password").value

        createUserWithEmailAndPassword(auth, email, password)
        .then((userCredential) => {
            const user = userCredential.user
            user.getIdToken().then((token) => {
                document.cookie = "token=" + token + ";path=/;SameSite=Strict";
                window.location = "/";
            });
        })
        .catch((error) => {
            console.log(error.code + error.message);
        })
    })

    document.getElementById("login").addEventListener('click', function() {
        const email    = document.getElementById("email").value
        const password = document.getElementById("password").value

        signInWithEmailAndPassword(auth, email, password)
        .then((userCredential) => {
            const user = userCredential.user;
            console.log("logged in");
            user.getIdToken().then((token) => {
                document.cookie = "token=" + token + ";path=/;SameSite=Strict";
                window.location = "/"
            });
        })
        .catch((error) => {
            console.log(error.code + error.message)
        });
    });

    document.getElementById("sign-out").addEventListener('click', function() {
        signOut(auth)
        .then((output) => {
            document.cookie = "token=;path=/;SameSite=Strict";
            window.location = "/";
        })
    });
});

function updateUI(cookie) {
    var token = parseCookieToken(cookie);
    if(token.length > 0) {
        document.getElementById("login-box").hidden  = true;
        document.getElementById("sign-out").hidden   = false;
    } else {
        document.getElementById("login-box").hidden  = false;
        document.getElementById("sign-out").hidden   = true;
    }
}

function parseCookieToken(cookie) {
    var strings = cookie.split(';');
    for(let i = 0; i < strings.length; i++) {
        var temp = strings[i].split('=');
        if(temp[0] == "token")
            return temp[1];
    }
    return ""
}