window.addEventListener('DOMContentLoaded', function () {
    const usernameField = document.getElementById('usernameField');
    if (usernameField) {
        usernameField.focus();
    }

    const hiddenPhone = document.getElementById('phone');
    if (hiddenPhone && hiddenPhone.value) {
        const parts = hiddenPhone.value.split('-');
        if (parts.length >= 1) p1.value = parts[0] || '';
        if (parts.length >= 2) p2.value = parts[1] || '';
        if (parts.length >= 3) p3.value = parts[2] || '';
    }
});

function togglePassword() {
    const pwdField = document.getElementById('passwordField');
    const toggleBtn = document.getElementById('togglePwBtn');
    if (pwdField.type === 'password') {
        pwdField.type = 'text';
        toggleBtn.textContent = '🔒 隠す';
    } else {
        pwdField.type = 'password';
        toggleBtn.textContent = '👁️ 表示';
    }
}

const p1 = document.getElementById('p1');
const p2 = document.getElementById('p2');
const p3 = document.getElementById('p3');

p1.addEventListener('input', function () {
    this.value = this.value.replace(/[^0-9]/g, '');
    const val = this.value;
    const mobilePrefixes = ['090', '080', '070', '060', '050'];
    if (val.length === 3 && mobilePrefixes.includes(val)) {
        p2.focus();
    } else if (val.length >= 4) {
        p2.focus();
    }
});

p2.addEventListener('input', function () {
    this.value = this.value.replace(/[^0-9]/g, '');
    if (this.value.length >= 4) {
        p3.focus();
    }
});

p3.addEventListener('input', function () {
    this.value = this.value.replace(/[^0-9]/g, '');
    if (this.value.length > 4) {
        this.value = this.value.slice(0, 4);
    }
});

p1.addEventListener('keydown', function (e) { if (e.key === 'Enter') { e.preventDefault(); p2.focus(); } });
p2.addEventListener('keydown', function (e) { if (e.key === 'Enter') { e.preventDefault(); p3.focus(); } });

function preparePhoneSubmit() {
    const val1 = p1.value.trim();
    const val2 = p2.value.trim();
    const val3 = p3.value.trim();

    const phoneField = document.getElementById('phone');
    if (phoneField) {
        phoneField.value = val1 + '-' + val2 + '-' + val3;
    }
}

document.getElementById('registerForm').addEventListener('submit', preparePhoneSubmit);
document.getElementById('togglePwBtn').addEventListener('click', togglePassword);
