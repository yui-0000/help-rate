const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
function setup() {
    const field = () => ({value: '', handlers: {}, addEventListener(event, fn) {this.handlers[event] = fn;},
        setCustomValidity(message) {this.error = message;}});
    const phone = field(), email = field(), feedback = {};
    const fields = {'[name="contact_phone"]': phone, '[name="contact_email"]': email, '[data-phone-feedback]': feedback};
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../static/js/contact-input.js'), 'utf8'), {
        document: {querySelectorAll() {return [{querySelector(selector) {return fields[selector];}}];}},
    });
    return {phone, email, feedback};
}
test('phone blocks a twelfth digit and overlong paste without truncating it', () => {
    const {phone} = setup();
    phone.value = '09012345678';
    let blocked = false;
    phone.handlers.beforeinput({inputType: 'insertText', data: '9', preventDefault() {blocked = true;}});
    assert.equal(blocked, true);
    assert.equal(phone.value, '09012345678');
    phone.value = '';
    blocked = false;
    phone.handlers.paste({clipboardData: {getData() {return '09012345678999';}}, preventDefault() {blocked = true;}});
    assert.equal(blocked, true);
    assert.equal(phone.value, '');
    phone.value = '09012345678'; phone.selectionStart = 3; phone.selectionEnd = 4;
    blocked = false;
    phone.handlers.beforeinput({inputType: 'insertText', data: '8', preventDefault() {blocked = true;}});
    assert.equal(blocked, false);
});
test('phone accepts mobile and fixed-line numbers and rejects invalid length', () => {
    const {phone} = setup();
    for (const value of ['090-1234-5678', '03-1234-5678', '０９０－１２３４－５６７８', '09012345678', '0312345678']) {
        phone.value = value; phone.handlers.input(); assert.equal(phone.error, '');
    }
    for (const value of ['090123', '090123456789', 'abc', '1234567890']) {
        phone.value = value; phone.handlers.input(); assert.notEqual(phone.error, '');
    }
});
test('email requires a complete domain after @ while allowing phone-only contact', () => {
    const {email} = setup();
    for (const value of ['', 'taro@example.com', 'taro@example.co.jp']) {
        email.value = value; email.handlers.input(); assert.equal(email.error, '');
    }
    for (const value of ['taro@', 'taro@example', 'taro@example.', 'taro@.com', 'taro@@example.com', 'taro@example..com']) {
        email.value = value; email.handlers.input(); assert.notEqual(email.error, '');
    }
});
