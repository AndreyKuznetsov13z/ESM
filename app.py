from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
import logging
from logging.handlers import RotatingFileHandler
from db import *
from functools import wraps
import os

app = Flask(__name__)
app.secret_key = 'SECRET_KEY_SOFTWARE_SHOP'

# Настройка логирования
handler = RotatingFileHandler('app.log', maxBytes=100000, backupCount=5)
handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logging.getLogger().addHandler(handler)
logging.getLogger().setLevel(logging.INFO)

# Отключение логов werkzeug для статических файлов
werkzeug_logger = logging.getLogger('werkzeug')
werkzeug_logger.setLevel(logging.ERROR)

# Инициализация базы данных при запуске приложения
init_db()
seed_initial_data()


# ======================== DECORATORS (ДЕКОРАТОРЫ) ========================

def login_required(f):
    """Проверка авторизации"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Вы должны войти в систему!', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    """Проверка прав администратора"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Вы должны войти в систему!', 'warning')
            return redirect(url_for('login'))
        
        user = get_user_by_id(session['user_id'])
        if not user or user['role'] != 'admin':
            flash('Доступ запрещён! Требуются права администратора.', 'danger')
            return redirect(url_for('index'))
        
        return f(*args, **kwargs)
    return decorated_function


# ======================== AUTHENTICATION (АУТЕНТИФИКАЦИЯ) ========================

@app.route('/register', methods=['GET', 'POST'])
def register():
    if 'user_id' in session:
        return redirect(url_for('index'))
    
    """Регистрация нового пользователя"""
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        name = request.form.get('name', '').strip()
        phone = request.form.get('phone', '').strip()
        accept_privacy = request.form.get('accept_privacy')
        
        # Валидация
        if not email or not password or not name:
            flash('Email, пароль и имя обязательны!', 'danger')
            return render_template('register.html')
        if not accept_privacy:
            flash('Для регистрации нужно принять политику конфиденциальности.', 'danger')
            return render_template('register.html')
        
        if len(password) < 6:
            flash('Пароль должен быть не менее 6 символов!', 'danger')
            return render_template('register.html')
        
        # Проверка существования пользователя
        if get_user_by_email(email):
            flash('Пользователь с таким email уже существует!', 'danger')
            return render_template('register.html')
        
        try:
            # Добавление пользователя (без хеширования для простоты)
            user_id = add_user(email, password, name, phone)
            flash('Регистрация успешна! Теперь войдите в систему.', 'success')
            logging.info(f'New user registered: {email} with ID: {user_id}')
            return redirect(url_for('login'))
        except Exception as e:
            flash(f'Ошибка регистрации: {str(e)}', 'danger')
            logging.error(f'Registration error: {e}')
            return render_template('register.html')
    
    return render_template('register.html')

@app.route('/privacy')
def privacy_policy():
    return render_template('privacy.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('index'))
    
    """Вход в систему"""
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        
        if not email or not password:
            flash('Email и пароль обязательны!', 'danger')
            return render_template('login.html')
        
        user = get_user_by_email(email)
        
        if user and user['password'] == password and user['is_active']:
            session['user_id'] = user['id']
            session['user_name'] = user['name']
            session['user_role'] = user['role']
            flash(f'Добро пожаловать, {user["name"]}!', 'success')
            logging.info(f'User logged in: {email}')
            return redirect(url_for('index'))
        else:
            flash('Неверный email или пароль!', 'danger')
            logging.warning(f'Failed login attempt for: {email}')
            return render_template('login.html')
    
    return render_template('login.html')


@app.route('/logout')
def logout():
    """Выход из системы"""
    user_name = session.get('user_name', 'Unknown')
    session.clear()
    flash('Вы вышли из системы.', 'info')
    logging.info(f'User logged out: {user_name}')
    return redirect(url_for('index'))


# ======================== MAIN PAGES (ОСНОВНЫЕ СТРАНИЦЫ) ========================
@app.route('/')
def index():
    """Главная страница"""
    software_list = get_bestsellers(limit=12)
    logging.info('Loaded main page with bestsellers')
    return render_template('index.html', software_list=software_list)


@app.route('/catalog')
def catalog():
    q = request.args.get('q', '').strip()
    category_id = request.args.get('category_id')
    price_min = request.args.get('price_min')
    price_max = request.args.get('price_max')

    cat_id_int = int(category_id) if category_id and category_id.isdigit() else None

    software_list = get_filtered_software(
        q=q,
        category_id=cat_id_int,
        price_min=price_min,
        price_max=price_max,
    )

    categories = get_all_categories()

    return render_template(
        'catalog.html',
        software_list=software_list,
        categories=categories,
    )


@app.route('/account')
@login_required
def account():
    user_id = session['user_id']
    user = get_user_by_id(user_id)

    recent_purchases = get_purchases_with_items(user_id, limit=5)
    cart_items = get_cart_items(user_id)
    total_cart = sum(item['quantity'] * item['price_at_add'] for item in cart_items)

    return render_template(
        'account.html',
        user=user,
        recent_purchases=recent_purchases,
        cart_items=cart_items,
        total_cart=total_cart,
    )


@app.route('/support', methods=['GET', 'POST'])
def support():
    user_id = session.get('user_id')
    user_name = session.get('user_name')
    user_email = session.get('user_email')  # если такое есть в сессии

    if request.method == 'POST':
        name = request.form.get('name') or user_name or 'Гость'
        email = request.form.get('email') or user_email or ''
        subject = request.form.get('subject', '').strip()
        message = request.form.get('message', '').strip()

        if not email or not subject or not message:
            flash('Email, тема и сообщение обязательны.', 'danger')
            return render_template('support.html')

        add_support_ticket(
            name=name,
            email=email,
            subject=subject,
            message=message,
            user_id=user_id,
        )

        flash(
            'Ваш тикет отправлен. Мы свяжемся с вами в ближайшее время.',
            'support'
        )
        return redirect(url_for('support'))

    return render_template('support.html')

@app.route('/software/<int:software_id>/review', methods=['POST'])
@login_required
def add_software_review(software_id):
    user_id = session.get('user_id')

    # проверяем, покупал ли пользователь этот софт
    if not user_has_purchased_software(user_id, software_id):
        flash('Оставлять отзывы могут только пользователи, купившие этот продукт.', 'danger')
        return redirect(url_for('software_detail', software_id=software_id))

    rating_raw = request.form.get('rating')
    text = request.form.get('comment', '').strip()

    try:
        rating = int(rating_raw)
    except (TypeError, ValueError):
        rating = 0

    if rating < 1 or rating > 5:
        flash('Оценка должна быть от 1 до 5.', 'danger')
        return redirect(url_for('software_detail', software_id=software_id))

    if not text:
        flash('Текст отзыва не должен быть пустым.', 'danger')
        return redirect(url_for('software_detail', software_id=software_id))

    add_or_update_review(user_id, software_id, rating, text)
    flash('Ваш отзыв сохранён.', 'success')
    return redirect(url_for('software_detail', software_id=software_id))



@app.route('/edit_profile', methods=['GET', 'POST'])
@login_required
def edit_profile():
    user_id = session['user_id']
    user = get_user_by_id(user_id)

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip()

        if not name or not email:
            flash('Имя и email обязательны', 'danger')
            return render_template('edit_profile.html', user=user)

        # Проверяем, что email не занят другим пользователем
        other = get_user_by_email(email)
        if other and other['id'] != user_id:
            flash('Пользователь с таким email уже существует.', 'email_error')

            user = dict(user)
            user['name'] = name
            user['email'] = email
            user['phone'] = phone

            return render_template('edit_profile.html', user=user)

        update_user_profile(user_id=user_id, name=name, email=email, phone=phone)
        flash('Данные профиля обновлены', 'success')
        return redirect(url_for('account'))

    return render_template('edit_profile.html', user=user)



@app.route('/software/<int:software_id>')
def software_detail(software_id):
    user_id = session.get('user_id')

    software = get_software_by_id(software_id)
    if not software:
        flash('Продукт не найден.', 'danger')
        return redirect(url_for('catalog'))

    reviews = get_reviews_for_software(software_id)

    can_review = False
    user_review = None
    if user_id:
        can_review = user_has_purchased_software(user_id, software_id)
        if can_review:
            user_review = get_user_review_for_software(user_id, software_id)

    return render_template(
        'software_detail.html',
        software=software,
        reviews=reviews,
        can_review=can_review,
        user_review=user_review,
    )


@app.route('/admin/reviews')
@login_required
def admin_reviews():
    user_role = session.get('user_role')
    if user_role not in ['admin', 'moder']:
        flash('Доступ к отзывам запрещён.', 'danger')
        return redirect(url_for('index'))

    reviews = get_recent_reviews(limit=200)

    return render_template(
        'admin_reviews.html',
        reviews=reviews,
    )



# ======================== CART (КОРЗИНА) ========================

@app.route('/cart')
@login_required
def cart():
    """Просмотр корзины"""
    user_id = session['user_id']
    cart = get_user_cart(user_id)
    cart_items = get_cart_items(user_id)
    
    logging.info(f'User {user_id} viewed cart with {len(cart_items)} items')
    
    return render_template('cart.html',
                         cart=cart,
                         cart_items=cart_items)


@app.route('/add_to_cart/<int:software_id>', methods=['POST'])
@login_required
def add_to_cart_route(software_id):
    """Добавить товар в корзину"""
    user_id = session['user_id']
    quantity = request.form.get('quantity', 1, type=int)
    
    if quantity <= 0:
        flash('Неверное количество!', 'danger')
        return redirect(request.referrer or url_for('catalog'))
    
    software = get_software_by_id(software_id)
    if not software:
        flash('Программа не найдена!', 'danger')
        return redirect(url_for('catalog'))
    
    try:
        add_to_cart(user_id, software_id, quantity)
        flash(f'"{software["name"]}" добавлено в корзину!', 'success')
        logging.info(f'User {user_id} added {software["name"]} to cart (qty: {quantity})')
    except Exception as e:
        flash(f'Ошибка: {str(e)}', 'danger')
        logging.error(f'Error adding to cart: {e}')
    
    return redirect(request.referrer or url_for('catalog'))


@app.route('/update_cart_item/<int:item_id>', methods=['POST'])
@login_required
def update_cart_item_route(item_id):
    """Обновить количество товара в корзине"""
    quantity = request.form.get('quantity', 1, type=int)
    
    if quantity <= 0:
        flash('Неверное количество!', 'danger')
        return redirect(url_for('cart'))
    
    try:
        update_cart_item_quantity(item_id, quantity)
        flash('Корзина обновлена!', 'success')
        logging.info(f'User updated cart item {item_id} to quantity {quantity}')
    except Exception as e:
        flash(f'Ошибка: {str(e)}', 'danger')
        logging.error(f'Error updating cart item: {e}')
    
    return redirect(url_for('cart'))


@app.route('/remove_from_cart/<int:item_id>', methods=['POST'])
@login_required
def remove_from_cart_route(item_id):
    """Удалить товар из корзины"""
    try:
        remove_from_cart(item_id)
        flash('Товар удален из корзины!', 'success')
        logging.info(f'Item {item_id} removed from cart')
    except Exception as e:
        flash(f'Ошибка: {str(e)}', 'danger')
        logging.error(f'Error removing from cart: {e}')
    
    return redirect(url_for('cart'))


@app.route('/clear_cart', methods=['POST'])
@login_required
def clear_cart_route():
    """Очистить корзину"""
    user_id = session['user_id']
    
    try:
        clear_cart(user_id)
        flash('Корзина очищена!', 'success')
        logging.info(f'User {user_id} cleared cart')
    except Exception as e:
        flash(f'Ошибка: {str(e)}', 'danger')
        logging.error(f'Error clearing cart: {e}')
    
    return redirect(url_for('cart'))


# ======================== CHECKOUT (ОФОРМЛЕНИЕ ПОКУПКИ) ========================

@app.route('/checkout', methods=['GET', 'POST'])
@login_required
def checkout():
    """Оформление покупки"""
    user_id = session['user_id']
    cart = get_user_cart(user_id)
    cart_items = get_cart_items(user_id)
    user = get_user_by_id(user_id)
    
    if not cart_items:
        flash('Ваша корзина пуста!', 'warning')
        return redirect(url_for('catalog'))
    
    if request.method == 'POST':
        payment_method = request.form.get('payment_method', 'card')
        
        try:
            purchase_id = create_purchase(user_id, payment_method)
            logging.info(f'Purchase created: {purchase_id} for user {user_id}')
            return redirect(url_for('purchase_success', purchase_id=purchase_id))
        except Exception as e:
            flash(f'Ошибка при оформлении покупки: {str(e)}', 'danger')
            logging.error(f'Checkout error: {e}')
    
    return render_template(
        'checkout.html',
        cart=cart,
        cart_items=cart_items,
        user=user,
    )


@app.route('/purchase_success/<int:purchase_id>')
@login_required
def purchase_success(purchase_id):
    """Страница успешной покупки"""
    purchase = get_purchase_by_id(purchase_id)
    purchase_items = get_purchase_items(purchase_id)
    
    if not purchase or purchase['user_id'] != session['user_id']:
        flash('Покупка не найдена!', 'danger')
        return redirect(url_for('index'))
    
    logging.info(f'Purchase success page viewed: {purchase_id}')
    
    return render_template('purchase_success.html',
                         purchase=purchase,
                         purchase_items=purchase_items)


# ======================== PURCHASES (ИСТОРИЯ ПОКУПОК) ========================

@app.route('/purchases')
@login_required
def purchases():
    user_id = session['user_id']
    purchases_list = get_purchases_with_items(user_id)

    logging.info(f'User {user_id} viewed purchase history')
    return render_template('purchases.html', purchases=purchases_list)



@app.route('/purchase_detail/<int:purchase_id>')
@login_required
def purchase_detail(purchase_id):
    """Детали покупки"""
    purchase = get_purchase_by_id(purchase_id)
    
    if not purchase or purchase['user_id'] != session['user_id']:
        flash('Покупка не найдена!', 'danger')
        return redirect(url_for('purchases'))
    
    purchase_items = get_purchase_items(purchase_id)
    
    logging.info(f'User {session["user_id"]} viewed purchase {purchase_id}')
    
    return render_template(
        'purchase_detail.html',
        purchase=purchase,
        purchase_items=purchase_items,
    )



# ======================== REVIEWS (ОТЗЫВЫ) ========================

@app.route('/add_review/<int:software_id>', methods=['POST'])
@login_required
def add_review_route(software_id):
    """Добавить отзыв"""
    user_id = session['user_id']
    rating = request.form.get('rating', 5, type=int)
    comment = request.form.get('comment', '').strip()
    
    if rating < 1 or rating > 5:
        flash('Рейтинг должен быть от 1 до 5!', 'danger')
        return redirect(url_for('software_detail', software_id=software_id))
    
    software = get_software_by_id(software_id)
    if not software:
        flash('Программа не найдена!', 'danger')
        return redirect(url_for('catalog'))
    
    try:
        add_review(user_id, software_id, rating, comment)
        flash('Спасибо за ваш отзыв!', 'success')
        logging.info(f'Review added for software {software_id} by user {user_id}')
    except sqlite3.IntegrityError:
        flash('Вы уже оставили отзыв на это ПО!', 'info')
    except Exception as e:
        flash(f'Ошибка: {str(e)}', 'danger')
        logging.error(f'Error adding review: {e}')
    
    return redirect(url_for('software_detail', software_id=software_id))


# ======================== ADMIN PANEL (АДМИН-ПАНЕЛЬ) ========================

@app.route('/admin_panel')
@login_required
def admin_panel():
    user_id = session.get('user_id')
    user = get_user_by_id(user_id)

    if not user or user['role'] != 'admin':
        flash('Доступ к админ-панели запрещён.', 'danger')
        return redirect(url_for('index'))

    stats = get_sales_statistics()

    health_status = {
        'database_accessible': check_db(),   # True / False
        'flask_running': True,
        'logging_enabled': True,
    }

    return render_template(
        'admin_panel.html',
        user_id=user_id,
        user=user,
        stats=stats,
        health_status=health_status,
    )

@app.route('/manage_software')
@login_required
def manage_software():
    user_role = session.get('user_role')
    user_id = session.get('user_id')

    if user_role not in ['admin', 'moder']:
        flash('Доступ к менеджменту ПО запрещён.', 'danger')
        return redirect(url_for('index'))

    user = get_user_by_id(user_id)
    software_list = get_all_software()

    return render_template(
        'manage_software.html',
        user_id=user_id,
        user=user,
        user_role=user_role,
        software_list=software_list,
    )

@app.route('/manage_software/add', methods=['GET', 'POST'])
@login_required
def add_software_page():
    user_role = session.get('user_role')
    if user_role not in ['admin', 'moder']:
        flash('Доступ запрещён.', 'danger')
        return redirect(url_for('index'))

    categories = get_all_categories()

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        price = request.form.get('price', '').strip()
        category_id = request.form.get('category_id')
        developer = request.form.get('developer', '').strip()
        image_url = request.form.get('image_url', '').strip() or None

        if not name or not price or not category_id or not developer:
            flash('Название, цена, категория и разработчик обязательны.', 'danger')
            return render_template('software_edit.html',
                                   mode='add',
                                   categories=categories)

        try:
            price_val = float(price)
        except ValueError:
            flash('Цена должна быть числом.', 'danger')
            return render_template('software_edit.html',
                                   mode='add',
                                   categories=categories)

        software_id = add_software(
            name=name,
            description=description,
            price=price_val,
            category_id=int(category_id),
            developer=developer,
            image_url=image_url
        )
        flash('ПО успешно добавлено.', 'success')
        return redirect(url_for('manage_software'))

    return render_template('software_edit.html',
                           mode='add',
                           categories=categories)


@app.route('/manage_software/<int:software_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_software_page(software_id):
    user_role = session.get('user_role')
    if user_role not in ['admin', 'moder']:
        flash('Доступ запрещён.', 'danger')
        return redirect(url_for('index'))

    software = get_software_by_id(software_id)
    if not software:
        flash('ПО не найдено.', 'danger')
        return redirect(url_for('manage_software'))

    categories = get_all_categories()

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        price = request.form.get('price', '').strip()
        category_id = request.form.get('category_id')
        developer = request.form.get('developer', '').strip()
        image_url = request.form.get('image_url', '').strip() or None

        if not name or not price or not category_id or not developer:
            flash('Название, цена, категория и разработчик обязательны.', 'danger')
            return render_template('software_edit.html',
                                   mode='edit',
                                   software=software,
                                   categories=categories)

        try:
            price_val = float(price)
        except ValueError:
            flash('Цена должна быть числом.', 'danger')
            return render_template('software_edit.html',
                                   mode='edit',
                                   software=software,
                                   categories=categories)

        update_software(
            software_id=software_id,
            name=name,
            description=description,
            price=price_val,
            category_id=int(category_id),
            developer=developer,
            image_url=image_url
        )
        flash('Данные ПО обновлены.', 'success')
        return redirect(url_for('manage_software'))

    return render_template('software_edit.html',
                           mode='edit',
                           software=software,
                           categories=categories)

@app.route('/manage_software/<int:software_id>/delete', methods=['POST'])
@login_required
def delete_software_route(software_id):
    user_role = session.get('user_role')
    if user_role not in ['admin', 'moder']:
        flash('Доступ запрещён.', 'danger')
        return redirect(url_for('index'))

    delete_software(software_id)
    flash('ПО удалено.', 'success')
    return redirect(url_for('manage_software'))

@app.route('/admin_users')
@login_required
def admin_users():
    user_role = session.get('user_role')
    if user_role != 'admin':
        flash('Доступ к управлению пользователями запрещён.', 'danger')
        return redirect(url_for('index'))

    q = request.args.get('q', '').strip()
    sort = request.args.get('sort', 'created_at')
    direction = request.args.get('direction', 'desc')

    users = search_users(
        q if q else None,
        sort=sort,
        direction=direction,
    )

    return render_template(
        'admin_users.html',
        users=users,
        search_query=q,
        current_sort=sort,
        current_direction=direction,
    )


@app.route('/admin/users/<int:user_id>/role', methods=['POST'])
@login_required
def admin_change_user_role(user_id):
    user_role = session.get('user_role')
    if user_role != 'admin':
        flash('Нет прав для изменения ролей.', 'danger')
        return redirect(url_for('admin_users'))

    new_role = request.form.get('role')
    if new_role not in ['user', 'moder', 'admin']:
        flash('Недопустимая роль.', 'danger')
        return redirect(url_for('admin_users'))

    set_user_role(user_id, new_role)
    flash('Роль пользователя обновлена.', 'success')
    return redirect(url_for('admin_users'))


@app.route('/admin/users/<int:user_id>/toggle_active', methods=['POST'])
@login_required
def admin_toggle_user_active(user_id):
    user_role = session.get('user_role')
    if user_role != 'admin':
        flash('Нет прав для блокировки пользователей.', 'danger')
        return redirect(url_for('admin_users'))

    u = get_user_by_id(user_id)
    if not u:
        flash('Пользователь не найден.', 'danger')
        return redirect(url_for('admin_users'))

    new_state = not bool(u['is_active'])
    set_user_active(user_id, new_state)

    flash('Статус пользователя обновлён.', 'success')
    return redirect(url_for('admin_users'))


@app.route('/admin/categories')
@login_required
def manage_categories():
    user_role = session.get('user_role')
    if user_role != 'admin':
        flash('Доступ к управлению категориями запрещён.', 'danger')
        return redirect(url_for('index'))

    categories = get_all_categories()
    return render_template('manage_categories.html', categories=categories)

@app.route('/admin/categories/add', methods=['POST'])
@login_required
def add_category_route():
    user_role = session.get('user_role')
    if user_role != 'admin':
        flash('Нет прав для добавления категорий.', 'danger')
        return redirect(url_for('manage_categories'))

    name = request.form.get('name', '').strip()
    description = request.form.get('description', '').strip() or None

    if not name:
        flash('Название категории обязательно.', 'danger')
        return redirect(url_for('manage_categories'))

    try:
        add_category(name, description)
        flash('Категория добавлена.', 'success')
    except Exception:
        flash('Ошибка: категория с таким названием уже существует.', 'danger')

    return redirect(url_for('manage_categories'))


@app.route('/admin/categories/<int:category_id>/edit', methods=['POST'])
@login_required
def edit_category_route(category_id):
    user_role = session.get('user_role')
    if user_role != 'admin':
        flash('Нет прав для изменения категорий.', 'danger')
        return redirect(url_for('manage_categories'))

    name = request.form.get('name', '').strip()
    description = request.form.get('description', '').strip() or None

    if not name:
        flash('Название категории обязательно.', 'danger')
        return redirect(url_for('manage_categories'))

    update_category(category_id, name=name, description=description)
    flash('Категория обновлена.', 'success')
    return redirect(url_for('manage_categories'))

@app.route('/admin/categories/<int:category_id>/delete', methods=['POST'])
@login_required
def delete_category_route(category_id):
    user_role = session.get('user_role')
    if user_role != 'admin':
        flash('Нет прав для удаления категорий.', 'danger')
        return redirect(url_for('manage_categories'))

    try:
        delete_category(category_id)
        flash('Категория удалена.', 'success')
    except Exception:
        flash('Невозможно удалить категорию: она используется в товарах.', 'danger')

    return redirect(url_for('manage_categories'))


@app.route('/admin/tickets')
@login_required
def admin_tickets():
    user_role = session.get('user_role')
    if user_role not in ['admin', 'moder']:
        flash('Доступ к тикетам запрещён.', 'danger')
        return redirect(url_for('index'))

    status = request.args.get('status', 'active')

    if status == 'all':
        tickets = get_tickets_by_status(None)
    elif status == 'active':
        tickets_new = get_tickets_by_status('new')
        tickets_in_progress = get_tickets_by_status('in_progress')
        tickets = tickets_new + tickets_in_progress
    else:
        tickets = get_tickets_by_status(status)

    return render_template(
        'admin_tickets.html',
        tickets=tickets,
        current_status=status,
    )

@app.route('/admin/tickets/<int:ticket_id>/status', methods=['POST'])
@login_required
def admin_ticket_change_status(ticket_id):
    user_role = session.get('user_role')
    if user_role not in ['admin', 'moder']:
        flash('Нет прав изменять статус тикетов.', 'danger')
        return redirect(url_for('admin_tickets'))

    new_status = request.form.get('status')
    try:
        update_ticket_status(ticket_id, new_status)
        flash('Статус тикета обновлён.', 'success')
    except ValueError:
        flash('Недопустимый статус.', 'danger')

    return redirect(url_for('admin_tickets', status=request.args.get('status', 'active')))

#====================================== ОШИБКА 404 0_о

@app.errorhandler(404)
def page_not_found(error):
    """Обработка ошибки 404"""
    logging.warning(f'Page not found: {request.path}')
    return render_template('404.html'), 404

#=====================================================

@app.context_processor
def inject_user():
    user_id = session.get('user_id')
    cart_count = 0
    active_tickets_count = 0

    if user_id:
        cart_items = get_cart_items(user_id)
        cart_count = len(cart_items)

    # Счётчик активных тикетов только для админки
    try:
        active_tickets_count = count_active_tickets()
    except Exception:
        active_tickets_count = 0

    return dict(
        user_id=user_id,
        user_name=session.get('user_name'),
        user_role=session.get('user_role'),
        cart_count=cart_count,
        active_tickets_count=active_tickets_count,
        categories=get_all_categories(),
    )



if __name__ == '__main__':
    print('Running Software Shop on http://127.0.0.1:5000/')
    app.run(debug=True)
