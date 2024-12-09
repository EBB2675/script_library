import os
import sys
import inspect
from plantuml import PlantUML

base_path = '/Users/esmaboydas/Desktop/NOMAD/dev/nomad-simulations/src'
package_path = os.path.join(base_path, 'nomad_simulations/schema_packages')
external_classes_file = '/Users/esmaboydas/Desktop/NOMAD/new_classes.txt'
output_path = '/Users/esmaboydas/Desktop/NOMAD/uml_new_classes.puml'

# PlantUML server URL
plantuml_server = 'http://www.plantuml.com/plantuml/img/'

# Add the base path to sys.path
sys.path.insert(0, base_path)

def read_new_classes_list(file_path):
    """Read the external file containing the list of new class names."""
    with open(file_path, 'r') as file:
        return {line.strip() for line in file if line.strip()}

def extract_classes_and_details(package_path, new_classes):
    """Extract classes, their quantities, subsections, and parent classes."""
    classes_with_details = []

    for root, _, files in os.walk(package_path):
        for file in files:
            if file.endswith('.py'):
                file_path = os.path.join(root, file)
                # Compute the correct module name
                relative_path = os.path.relpath(file_path, base_path)
                module_name = relative_path.replace(os.sep, ".").rstrip(".py")
                print(f"Processing module: {module_name}")  # Debugging

                try:
                    spec = __import__(module_name, fromlist=["*"])
                except ImportError as e:
                    print(f"Error importing {module_name}: {e}")
                    continue

                for name, obj in inspect.getmembers(spec, inspect.isclass):
                    # Only process classes that are in the new_classes list
                    if name in new_classes:
                        print(f"Found class: {name}")  # Debugging
                        if inspect.getmodule(obj).__file__ == file_path:
                            parent_classes = [cls.__name__ for cls in obj.__bases__ if cls.__name__ != 'object']
                            quantities = [
                                member_name for member_name, member in inspect.getmembers(obj)
                                if "Quantity" in str(type(member))
                            ]
                            subsections = [
                                member_name for member_name, member in inspect.getmembers(obj)
                                if "SubSection" in str(type(member))
                            ]
                            classes_with_details.append((name, parent_classes, quantities, subsections))

    return classes_with_details

def generate_uml(classes_with_details, output_path):
    """Generate a UML .puml file with inheritance and subsections."""
    with open(output_path, 'w') as uml_file:
        uml_file.write('@startuml\n')

        # Write classes with their details
        for class_name, parent_classes, quantities, subsections in classes_with_details:
            uml_file.write(f'class {class_name} {{\n')

            # Add Quantities
            if quantities:
                uml_file.write('  // Quantities\n')
                for quantity in quantities:
                    uml_file.write(f'    {quantity}\n')

            # Add SubSections
            if subsections:
                uml_file.write('  // SubSections\n')
                for subsection in subsections:
                    uml_file.write(f'    {subsection} : SubSection\n')

            uml_file.write('}\n')

            # Write inheritance relationships
            for parent in parent_classes:
                uml_file.write(f'{parent} <|-- {class_name}\n')

        uml_file.write('@enduml\n')

def generate_diagram(uml_file_path):
    """Generate a UML diagram from the .puml file."""
    plantuml = PlantUML(url=plantuml_server)
    plantuml.processes_file(uml_file_path)

if __name__ == '__main__':
    # Step 1: Read the new classes list from the external file
    new_classes = read_new_classes_list(external_classes_file)

    # Step 2: Extract class details (quantities, subsections, and parent classes)
    classes_with_details = extract_classes_and_details(package_path, new_classes)

    # Step 3: Generate UML .puml file with inheritance and subsections
    generate_uml(classes_with_details, output_path)

    # Step 4: Generate UML diagram from the .puml file
    generate_diagram(output_path)

    print(f"UML diagram saved to {output_path}.")
