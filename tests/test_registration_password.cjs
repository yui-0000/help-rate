const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

test('password visibility controls toggle independently with accessible state', () => {
    const ids = {};
    for (const id of ['passwordField', 'confirmPasswordField', 'togglePwBtn', 'toggleConfirmPwBtn', 'registerForm', 'p1', 'p2', 'p3']) {
        ids[id] = {type: 'password', handlers: {}, attributes: {},
            addEventListener(event, fn) {this.handlers[event] = fn;},
            setAttribute(name, value) {this.attributes[name] = value;},
        };
    }
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../static/js/register.js'), 'utf8'), {
        document: {getElementById: id => ids[id]},
        window: {addEventListener() {}},
    });
    ids.toggleConfirmPwBtn.handlers.click();
    assert.equal(ids.confirmPasswordField.type, 'text');
    assert.equal(ids.passwordField.type, 'password');
    assert.equal(ids.toggleConfirmPwBtn.attributes['aria-pressed'], 'true');
    assert.equal(ids.toggleConfirmPwBtn.textContent, '🔒 隠す');
    ids.togglePwBtn.handlers.click();
    assert.equal(ids.passwordField.type, 'text');
    assert.equal(ids.confirmPasswordField.type, 'text');
    ids.toggleConfirmPwBtn.handlers.click();
    assert.equal(ids.confirmPasswordField.type, 'password');
    assert.equal(ids.passwordField.type, 'text');
    assert.equal(ids.toggleConfirmPwBtn.attributes['aria-pressed'], 'false');
    assert.equal(ids.toggleConfirmPwBtn.attributes['aria-label'], '確認用パスワードを表示');
    ids.togglePwBtn.handlers.click();
    assert.equal(ids.passwordField.type, 'password');
    assert.equal(ids.togglePwBtn.textContent, '👁️ 表示');
});
