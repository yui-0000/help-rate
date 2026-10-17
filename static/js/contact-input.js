document.querySelectorAll('.post-contact-fields').forEach((section) => {
    const phone = section.querySelector('[name="contact_phone"]');
    const email = section.querySelector('[name="contact_email"]');
    const feedback = section.querySelector('[data-phone-feedback]');
    const normalize = (value) => value.normalize('NFKC').trim();
    const withinPhoneLimit = (value) => {
        const text = normalize(value);
        return /^[0-9-]*$/.test(text) && text.replace(/-/g, '').length <= 11 &&
            (text.match(/-/g) || []).length <= 2 && text.length <= 13;
    };
    const replacement = (insert) => phone.value.slice(0, phone.selectionStart ?? phone.value.length) + insert +
        phone.value.slice(phone.selectionEnd ?? phone.value.length);
    const limitMessage = '電話番号は数字11桁まで、ハイフンは2つまで入力できます。';
    phone.addEventListener('beforeinput', (event) => {
        if (event.isComposing || !event.inputType.startsWith('insert') || event.data == null) return;
        if (!withinPhoneLimit(replacement(event.data))) {
            event.preventDefault();
            feedback.textContent = limitMessage;
        }
    });
    phone.addEventListener('paste', (event) => {
        const inserted = event.clipboardData?.getData('text');
        if (inserted != null && !withinPhoneLimit(replacement(inserted))) {
            event.preventDefault();
            feedback.textContent = limitMessage + ' 貼り付けた内容を確認してください。';
        }
    });
    function checkPhone() {
        const value = normalize(phone.value);
        const digits = value.replace(/-/g, '');
        const valid = !value || (withinPhoneLimit(value) && /^0[0-9]{9,10}$/.test(digits));
        phone.setCustomValidity(valid ? '' : '電話番号は0から始まる10〜11桁で入力してください。');
        feedback.textContent = valid ? '' : '電話番号は0から始まる10〜11桁で入力してください。';
    }
    function checkEmail() {
        const value = email.value.trim();
        const valid = !value || /^[^\s@]+@[^\s@.]+(?:\.[^\s@.]+)+$/.test(value);
        email.setCustomValidity(valid ? '' : '@の後ろも含め、正しいメールアドレスを入力してください（例：taro@example.com）。');
    }
    phone.addEventListener('input', checkPhone);
    email.addEventListener('input', checkEmail);
    checkPhone();
    checkEmail();
});
