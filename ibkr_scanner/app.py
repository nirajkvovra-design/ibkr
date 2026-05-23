from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os
import uuid

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///portfolio.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Database Models
class BlogPost(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(50), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class PortfolioProject(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    technologies = db.Column(db.String(200), nullable=False)
    github_link = db.Column(db.String(200))
    live_link = db.Column(db.String(200))
    image_url = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class FitnessPlan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    price = db.Column(db.Float, nullable=False)
    duration_weeks = db.Column(db.Integer, nullable=False)
    features = db.Column(db.Text, nullable=False)
    image_url = db.Column(db.String(200))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_number = db.Column(db.String(50), unique=True, nullable=False)
    fitness_plan_id = db.Column(db.Integer, db.ForeignKey('fitness_plan.id'), nullable=False)
    customer_name = db.Column(db.String(200), nullable=False)
    customer_email = db.Column(db.String(200), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    payment_method = db.Column(db.String(50), nullable=False)
    payment_status = db.Column(db.String(50), default='pending')
    transaction_id = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationship
    fitness_plan = db.relationship('FitnessPlan', backref='orders')

# Routes
@app.route('/')
def home():
    return render_template('home.html')

@app.route('/portfolio')
def portfolio():
    projects = PortfolioProject.query.order_by(PortfolioProject.created_at.desc()).all()
    return render_template('portfolio.html', projects=projects)

@app.route('/blog')
def blog():
    category = request.args.get('category', 'all')
    if category == 'all':
        posts = BlogPost.query.order_by(BlogPost.created_at.desc()).all()
    else:
        posts = BlogPost.query.filter_by(category=category).order_by(BlogPost.created_at.desc()).all()
    return render_template('blog.html', posts=posts, current_category=category)

@app.route('/blog/<int:post_id>')
def blog_post(post_id):
    post = BlogPost.query.get_or_404(post_id)
    return render_template('blog_post.html', post=post)

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/contact')
def contact():
    return render_template('contact.html')

@app.route('/fitness-plans')
def fitness_plans():
    plans = FitnessPlan.query.filter_by(is_active=True).all()
    return render_template('fitness_plans.html', plans=plans)

@app.route('/fitness-plans/<int:plan_id>')
def fitness_plan_detail(plan_id):
    plan = FitnessPlan.query.get_or_404(plan_id)
    return render_template('fitness_plan_detail.html', plan=plan)

@app.route('/checkout/<int:plan_id>', methods=['GET', 'POST'])
def checkout(plan_id):
    plan = FitnessPlan.query.get_or_404(plan_id)
    
    if request.method == 'POST':
        # Generate unique order number
        order_number = f"ORD-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"
        
        # Create order
        order = Order(
            order_number=order_number,
            fitness_plan_id=plan.id,
            customer_name=request.form['customer_name'],
            customer_email=request.form['customer_email'],
            amount=plan.price,
            payment_method=request.form['payment_method']
        )
        
        db.session.add(order)
        db.session.commit()
        
        # Redirect to payment processing
        return redirect(url_for('process_payment', order_id=order.id))
    
    return render_template('checkout.html', plan=plan)

@app.route('/process-payment/<int:order_id>')
def process_payment(order_id):
    order = Order.query.get_or_404(order_id)
    return render_template('payment_processing.html', order=order)

@app.route('/payment-success/<int:order_id>')
def payment_success(order_id):
    order = Order.query.get_or_404(order_id)
    order.payment_status = 'completed'
    order.transaction_id = f"TXN-{uuid.uuid4().hex[:12].upper()}"
    db.session.commit()
    
    flash('Payment successful! Your fitness plan will be delivered to your email.', 'success')
    return render_template('payment_success.html', order=order)

@app.route('/payment-cancelled/<int:order_id>')
def payment_cancelled(order_id):
    order = Order.query.get_or_404(order_id)
    order.payment_status = 'cancelled'
    db.session.commit()
    
    flash('Payment was cancelled. You can try again anytime.', 'warning')
    return redirect(url_for('fitness_plans'))

# Admin routes for blog management
@app.route('/admin/blog/new', methods=['GET', 'POST'])
def new_blog_post():
    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']
        category = request.form['category']
        
        post = BlogPost(title=title, content=content, category=category)
        db.session.add(post)
        db.session.commit()
        
        flash('Blog post created successfully!', 'success')
        return redirect(url_for('blog'))
    
    return render_template('admin/new_post.html')

@app.route('/admin/blog/<int:post_id>/edit', methods=['GET', 'POST'])
def edit_blog_post(post_id):
    post = BlogPost.query.get_or_404(post_id)
    
    if request.method == 'POST':
        post.title = request.form['title']
        post.content = request.form['content']
        post.category = request.form['category']
        post.updated_at = datetime.utcnow()
        
        db.session.commit()
        flash('Blog post updated successfully!', 'success')
        return redirect(url_for('blog_post', post_id=post.id))
    
    return render_template('admin/edit_post.html', post=post)

@app.route('/admin/blog/<int:post_id>/delete', methods=['POST'])
def delete_blog_post(post_id):
    post = BlogPost.query.get_or_404(post_id)
    db.session.delete(post)
    db.session.commit()
    flash('Blog post deleted successfully!', 'success')
    return redirect(url_for('blog'))

# Admin routes for fitness plans
@app.route('/admin/fitness-plans/new', methods=['GET', 'POST'])
def new_fitness_plan():
    if request.method == 'POST':
        plan = FitnessPlan(
            name=request.form['name'],
            description=request.form['description'],
            price=float(request.form['price']),
            duration_weeks=int(request.form['duration_weeks']),
            features=request.form['features'],
            image_url=request.form['image_url']
        )
        db.session.add(plan)
        db.session.commit()
        
        flash('Fitness plan created successfully!', 'success')
        return redirect(url_for('fitness_plans'))
    
    return render_template('admin/new_fitness_plan.html')

@app.route('/admin/fitness-plans/<int:plan_id>/edit', methods=['GET', 'POST'])
def edit_fitness_plan(plan_id):
    plan = FitnessPlan.query.get_or_404(plan_id)
    
    if request.method == 'POST':
        plan.name = request.form['name']
        plan.description = request.form['description']
        plan.price = float(request.form['price'])
        plan.duration_weeks = int(request.form['duration_weeks'])
        plan.features = request.form['features']
        plan.image_url = request.form['image_url']
        plan.is_active = 'is_active' in request.form
        
        db.session.commit()
        flash('Fitness plan updated successfully!', 'success')
        return redirect(url_for('fitness_plans'))
    
    return render_template('admin/edit_fitness_plan.html', plan=plan)

@app.route('/admin/fitness-plans/<int:plan_id>/delete', methods=['POST'])
def delete_fitness_plan(plan_id):
    plan = FitnessPlan.query.get_or_404(plan_id)
    db.session.delete(plan)
    db.session.commit()
    flash('Fitness plan deleted successfully!', 'success')
    return redirect(url_for('fitness_plans'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        
        # Create sample fitness plans if none exist
        if not FitnessPlan.query.first():
            sample_plans = [
                FitnessPlan(
                    name="Beginner Fitness Starter",
                    description="Perfect for those just starting their fitness journey. Includes basic workouts, nutrition guidance, and progress tracking.",
                    price=29.99,
                    duration_weeks=8,
                    features="8-week workout plan, Nutrition guide, Progress tracker, Video demonstrations, Email support",
                    image_url="https://images.unsplash.com/photo-1571019613454-1cb2f99b2d8b?w=400&h=300&fit=crop"
                ),
                FitnessPlan(
                    name="Intermediate Strength Builder",
                    description="Take your fitness to the next level with this comprehensive strength training program.",
                    price=49.99,
                    duration_weeks=12,
                    features="12-week strength program, Advanced nutrition, Recovery protocols, Personal consultation, Community access",
                    image_url="https://images.unsplash.com/photo-1571019613454-1cb2f99b2d8b?w=400&h=300&fit=crop"
                ),
                FitnessPlan(
                    name="Advanced Athlete Elite",
                    description="Elite-level training program for serious athletes and fitness enthusiasts.",
                    price=99.99,
                    duration_weeks=16,
                    features="16-week elite program, Custom meal plans, Performance analytics, 1-on-1 coaching, Priority support",
                    image_url="https://images.unsplash.com/photo-1571019613454-1cb2f99b2d8b?w=400&h=300&fit=crop"
                )
            ]
            
            for plan in sample_plans:
                db.session.add(plan)
            
            db.session.commit()
            print("Sample fitness plans created!")
    
    app.run(debug=True)
