#!/usr/bin/env python3
"""
EVENT LOOP ERROR DEMONSTRATION
Shows various ways to trigger "This event loop is already running" error
"""

import asyncio
import time
import threading

def demonstrate_error_from_sync_context():
    """Demonstrate error when calling asyncio.run() from sync context that already has a loop"""
    print("\n🔍 Method 1: Error from sync context with existing loop")
    print("-" * 50)
    
    async def simple_coro():
        await asyncio.sleep(0.1)
        return "Hello from coroutine"
    
    try:
        # This will work normally
        result = asyncio.run(simple_coro())
        print(f"✅ First asyncio.run() successful: {result}")
        
        # This will fail with "This event loop is already running"
        print("⚠️  Attempting second asyncio.run()...")
        result2 = asyncio.run(simple_coro())
        print(f"✅ Second asyncio.run() successful: {result2}")
        
    except RuntimeError as e:
        if "This event loop is already running" in str(e):
            print(f"❌ Event loop error caught: {e}")
            print("💡 This happens because asyncio.run() creates a new event loop")
            print("   but the previous one is still in memory/state")
        else:
            print(f"❌ Other runtime error: {e}")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")

def demonstrate_error_from_thread():
    """Demonstrate error when trying to run event loop from a thread"""
    print("\n🔍 Method 2: Error from thread context")
    print("-" * 50)
    
    async def thread_coro():
        await asyncio.sleep(0.1)
        return "Hello from thread coroutine"
    
    def run_in_thread():
        try:
            print("🧵 Running asyncio.run() from thread...")
            result = asyncio.run(thread_coro())
            print(f"✅ Thread asyncio.run() successful: {result}")
        except RuntimeError as e:
            if "This event loop is already running" in str(e):
                print(f"❌ Thread event loop error: {e}")
            else:
                print(f"❌ Other thread runtime error: {e}")
        except Exception as e:
            print(f"❌ Thread unexpected error: {e}")
    
    # Start thread
    thread = threading.Thread(target=run_in_thread)
    thread.start()
    thread.join()

def demonstrate_error_from_nested_async():
    """Demonstrate error when trying to run event loop from within async context"""
    print("\n🔍 Method 3: Error from nested async context")
    print("-" * 50)
    
    async def outer_coro():
        print("🔄 In outer coroutine...")
        
        async def inner_coro():
            await asyncio.sleep(0.1)
            return "Hello from inner coroutine"
        
        try:
            print("⚠️  Attempting asyncio.run() from within async context...")
            # This will cause the error
            result = asyncio.run(inner_coro())
            print(f"✅ Nested asyncio.run() successful: {result}")
        except RuntimeError as e:
            if "This event loop is already running" in str(e):
                print(f"❌ Nested event loop error: {e}")
                print("💡 This happens because we're already inside an event loop")
            else:
                print(f"❌ Other nested runtime error: {e}")
        except Exception as e:
            print(f"❌ Nested unexpected error: {e}")
        
        return "Outer coroutine completed"
    
    try:
        result = asyncio.run(outer_coro())
        print(f"✅ Outer coroutine result: {result}")
    except Exception as e:
        print(f"❌ Outer coroutine error: {e}")

def demonstrate_error_from_gui_context():
    """Demonstrate error that commonly occurs in GUI applications"""
    print("\n🔍 Method 4: Error from GUI-like context")
    print("-" * 50)
    
    async def gui_coro():
        await asyncio.sleep(0.1)
        return "Hello from GUI coroutine"
    
    def simulate_gui_context():
        """Simulate a GUI context where an event loop might already be running"""
        try:
            # Simulate getting an existing event loop
            loop = asyncio.get_event_loop()
            print(f"📋 Current event loop: {loop}")
            print(f"📋 Is running: {loop.is_running()}")
            
            # Try to run a new event loop (this will cause the error)
            print("⚠️  Attempting to run new event loop...")
            result = asyncio.run(gui_coro())
            print(f"✅ New event loop successful: {result}")
            
        except RuntimeError as e:
            if "This event loop is already running" in str(e):
                print(f"❌ GUI context event loop error: {e}")
                print("💡 This commonly happens in GUI applications like tkinter, PyQt, etc.")
            else:
                print(f"❌ Other GUI runtime error: {e}")
        except Exception as e:
            print(f"❌ GUI unexpected error: {e}")
    
    simulate_gui_context()

def demonstrate_solutions():
    """Demonstrate solutions to the event loop error"""
    print("\n🔍 Method 5: Solutions to event loop errors")
    print("-" * 50)
    
    async def solution_coro():
        await asyncio.sleep(0.1)
        return "Hello from solution coroutine"
    
    print("💡 Solution 1: Use asyncio.create_task() instead of asyncio.run()")
    print("💡 Solution 2: Use asyncio.ensure_future()")
    print("💡 Solution 3: Use the existing event loop with loop.create_task()")
    print("💡 Solution 4: Use asyncio.gather() for multiple coroutines")
    
    # Example of proper async usage
    async def proper_async_usage():
        print("🔄 Demonstrating proper async usage...")
        
        # Create tasks instead of trying to run new event loops
        task1 = asyncio.create_task(solution_coro())
        task2 = asyncio.create_task(solution_coro())
        
        # Wait for both tasks
        results = await asyncio.gather(task1, task2)
        print(f"✅ Proper async results: {results}")
        
        return "Proper async usage completed"
    
    try:
        result = asyncio.run(proper_async_usage())
        print(f"✅ {result}")
    except Exception as e:
        print(f"❌ Proper async usage error: {e}")

def main():
    """Main function to run all demonstrations"""
    print("🚀 EVENT LOOP ERROR DEMONSTRATION")
    print("=" * 60)
    print("This script demonstrates various ways to trigger")
    print("'This event loop is already running' error")
    print("=" * 60)
    
    # Run all demonstrations
    demonstrate_error_from_sync_context()
    demonstrate_error_from_thread()
    demonstrate_error_from_nested_async()
    demonstrate_error_from_gui_context()
    demonstrate_solutions()
    
    print("\n" + "=" * 60)
    print("🎯 DEMONSTRATION COMPLETE")
    print("=" * 60)
    print("Key takeaways:")
    print("• Don't use asyncio.run() from within async contexts")
    print("• Don't use asyncio.run() from threads with existing loops")
    print("• Use asyncio.create_task() and asyncio.gather() instead")
    print("• Be careful in GUI applications and Jupyter notebooks")

if __name__ == "__main__":
    main()


