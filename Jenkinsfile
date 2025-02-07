pipeline {
    agent any
    options {
        skipDefaultCheckout(true)
    }
    environment {
        INSTANCE_ID = "${params.INSTANCE_ID}" // Dla prostoty dostępu
        AWS_REGION = 'us-east-1'
    }

    stages {
         stage('Check and Start AWS Machine') {
             agent {
                label 'built-in' // Wymuszenie wykonania na "Built-In Node"
             }

            steps {
                script {
                        // Używaj parametru INSTANCE_ID przekazywanego do joba
                        def instanceID = env.INSTANCE_ID

                        echo "Using instance ID: ${instanceID}"

                        // Logika operacji AWS
                        def instanceState = sh(
                            script: """
                            aws ec2 describe-instances \
                                --instance-ids ${instanceID} \
                                --query "Reservations[0].Instances[0].State.Name" \
                                --output text \
                                --region ${env.AWS_REGION}
                            """,
                            returnStdout: true
                        ).trim()

                        echo "Current state of AWS instance ${instanceID}: ${instanceState}"

                        if (instanceState == "terminated") {
                            error "AWS instance ${instanceID} has been terminated. Cannot start it. Please recreate the instance."
                        } else if (instanceState != "running") {
                            echo "Starting AWS instance..."
                            sh """
                            aws ec2 start-instances --instance-ids ${instanceID} --region ${env.AWS_REGION}
                            """
                            sh """
                            aws ec2 wait instance-running --instance-ids ${instanceID} --region ${env.AWS_REGION}
                            """
                            echo "AWS instance ${instanceID} is now running."
                        } else {
                            echo "AWS instance ${instanceID} is already running."
                        }
                    }
                }
         }

         stage('Code checkout from GitHub') {
             agent {
                label 'aws-ec2-runner'
             }
            steps {
                script {
                    cleanWs()
                    git credentialsId: 'github-token', url: 'https://github.com/ziutus/ai_assistant_lenie_server', branch: 'main'
                }
            }
        }
        stage('Example') {
             agent {
                label 'aws-ec2-runner'
             }
            steps {
                echo 'Hello!'
                sh 'ls -la'
            }
        }
//         stage('Check file') {
//             steps {
//                 echo 'checking if file exist'
//                 sh 'ls -l passive_scan.yaml'
//             }
//         }
        stage('report dir creation') {
             agent {
                label 'aws-ec2-runner'
             }
            steps {
                echo 'create directory for reports'
                sh 'mkdir ${WORKSPACE}/results/'
            }
        }
        stage('check workspace') {
             agent {
                label 'aws-ec2-runner'
             }
            steps {
                echo 'checking if file exist'
                sh 'ls -l "$WORKSPACE"'
            }
        }




    stage('Run Semgrep Security Check') {
            agent {
                label 'aws-ec2-runner' // Wskazuje runner Jenkinsa komplementarny do tego w GitLab (np. AWS EC2)
            }
            steps {
                script {
                    echo 'Running Semgrep Security Check'

                    // Instalacja Semgrep (np. w środowisku Python)
                    sh '''
                        pip install semgrep
                    '''

                    // Uruchomienie Semgrep z zapisem raportu
                    sh '''
                        semgrep --config=auto --output semgrep-report.json || true
                    '''

                    // Tworzenie i zapisywanie raportu jako artefaktu
                    echo 'Storing Semgrep report as an artifact'
                    sh '''
                        mkdir -p ${WORKSPACE}/results/
                        mv semgrep-report.json ${WORKSPACE}/results/
                    '''
                }
            }
            post {
                always {
                    echo 'Archiving Semgrep report'
                    archiveArtifacts artifacts: 'results/semgrep-report.json', fingerprint: true
                }
                cleanup {
                    echo 'Cleaning up workspace post Semgrep stage'
                    cleanWs()
                }
            }
    }

    stage('Run TruffleHog Scan') {
        agent {
            label 'aws-ec2-runner' // Wskazuje agenta Jenkins używanego do uruchomienia kroku
        }
        steps {
            script {
                echo 'Running TruffleHog Secret Detection'

                // Tworzymy katalog na raporty
                echo 'Ensuring results directory exists...'
                sh 'mkdir -p results/'

                // Uruchamiamy kontener TruffleHog i zapisujemy logi w pliku
                sh '''
                    docker run --rm --name trufflehog \
                        trufflesecurity/trufflehog:latest git file://. \
                        --only-verified --bare 2>&1 | tee results/trufflehog.txt
                '''
            }
        }
        post {
            always {
                // Archiwizowanie raportu jako artefakt
                echo 'Archiving TruffleHog report'
                archiveArtifacts artifacts: 'results/trufflehog.txt', fingerprint: true
            }
            cleanup {
                // Czyszczenie workspace po wykonaniu kroku
                echo 'Cleaning up workspace after TruffleHog scan'
                cleanWs()
            }
        }
    }

    //    NIE DZIAŁA, trzeba sprawdzić
    //stage('Run OSV Scanner') {
    //    agent {
    //        label 'aws-ec2-runner' // Agregat, który był używany w twoich innych zadaniach
    //    }
    //    steps {
    //        script {
    //            echo 'Running OSV Scanner'
    //
    //            // Tworzymy katalog na wyniki skanowania
    //            sh 'mkdir -p results/'
    //
    //            // Uruchamiamy OSV Scanner z zależnościami określonymi w requirements.txt
    //            sh '''
    //                /usr/local/bin/osv-scanner scan --lockfile requirements.txt
    //            '''
    //        }
    //    }
    //    post {
    //        always {
    //            // Archiwizowanie wygenerowanego raportu OSV Scanner
    //            echo 'Archiving OSV Scanner results'
    //            archiveArtifacts artifacts: 'results/osv_scan_results.json', fingerprint: true
    //        }
    //        cleanup {
    //            // Oczyszczanie przestrzeni roboczej po zakończeniu
    //            echo 'Cleaning up workspace after OSV scan'
    //            cleanWs()
    //        }
    //    }
    //}

    stage('Python tests') {
        parallel {

            stage('Run Pytest') {
                agent {
                    label 'aws-ec2-runner' // Wskazanie runnera w Jenkins odpowiadającego GitLabowi (np. AWS)
                }
                steps {
                    script {
                        // Instalacja wymaganych zależności Python
                        echo 'Installing requirements...'
                        sh """
                        pip install -r requirements.txt
                        """

                        // Tworzenie katalogu na wyniki jeżeli nie istnieje
                        echo 'Ensuring results directory exists...'
                        sh """
                        mkdir -p pytest-results
                        """

                        // Uruchomienie testów i generacja raportu w HTML
                        echo 'Running Pytest...'
                        sh """
                        pytest --self-contained-html --html=pytest-results/report.html || true
                        """


                    }

                    // Zrzucenie katalogu wyników do logów Jenkins
                    echo 'Archiving test results...'
                    archiveArtifacts artifacts: 'pytest-results/**/*', allowEmptyArchive: true
                }
                post {
                    always {
                        echo 'Pytest stage completed. Results saved as artifacts.'
                    }
                }
            }

        stage('Run Flake8 Style Check') {
            agent {
                label 'aws-ec2-runner' // Agent odpowiadający tagom w GitLab-CI
            }
            steps {
                script {
                    echo 'Running Flake8 Style Check'

                    // Instalacja pakietu flake8-html
                    echo 'Installing flake8-html'
                    sh '''
                        python3 -m pip install --upgrade pip
                        pip3 install flake8-html
                    '''

                    // Uruchomienie Flake8 i zapis raportów HTML
                    echo 'Running Flake8 and generating HTML report'
                    sh '''
                        mkdir -p flake_reports
                        flake8 --format=html --htmldir=flake_reports/
                    '''
                }
            }
            post {
                always {
                    // Archiwizacja wyników Flake8 jako artefakt
                    echo 'Archiving Flake8 HTML Report'
                    archiveArtifacts artifacts: 'flake_reports/**', fingerprint: true
                }
                cleanup {
                    echo 'Cleaning up workspace after Flake8 scan'
                    cleanWs()
                }
            }
        }

    }


//          stage('[ZAP] Baseline passive-scan') {
// 			steps {
// 				sh '''
// 					docker run --name juice-shop -d \
// 						-p 3000:3000 \
// 						bkimminich/juice-shop
// 					sleep 5
// 				'''
// 				sh '''
// 					docker run --name zap  \
// 						--add-host=host.docker.internal:host-gateway \
// 						-v zap_config:/zap/wrk/:rw \
// 						-t ghcr.io/zaproxy/zaproxy:stable bash -c \
// 						"ls -l /zap/wrk/; zap.sh -cmd -addonupdate; zap.sh -cmd -addoninstall communityScripts -addoninstall pscanrulesAlpha -addoninstall pscanrulesBeta -autorun /zap/wrk/passive_scan.yaml" \
// 						|| true
// 				'''
// 			}
// 	    }
// 	    stage('Copy ZAP report') {
// 		    steps {
// 			sh '''
// 				docker run --rm -d -v zap_config:/app --name busybox busybox sh -c "sleep 4000"
// 		  		docker cp busybox:/app/reports/zap_xml_report.xml ${WORKSPACE}/results/zap_xml_report.xml
// 		 	'''
// 		    }
// 	    }

    }
//     post {
//         always {

//             sh '''
// 				ls -l /zap/wrk/passive_scan.yaml
// 				docker stop busybox
//             '''
		// docker stop trufflehog
		// defectDojoPublisher(artifact: '/zap/wrk/results/semgrep-report.json',
		//     productName: 'Juice Shop',
		//     scanType: 'Semgrep JSON Report',
		//     engagementName: 'krzysztof@odkrywca.eu')
//        }
//     }
    post {
        always {
            // Zatrzymywanie instancji EC2 po zakończeniu pipeline
            node('built-in') { // Wykonywane wyłącznie na "Built-In Node"
                script {
                    echo "Attempting to stop AWS EC2 instance..."
                    try {
                        sh """
                        aws ec2 stop-instances --instance-ids ${env.INSTANCE_ID} --region ${env.AWS_REGION}
                        """
                        sh """
                        aws ec2 wait instance-stopped --instance-ids ${env.INSTANCE_ID} --region ${env.AWS_REGION}
                        """
                        echo "AWS instance ${env.INSTANCE_ID} has been successfully stopped."
                    } catch (err) {
                        echo "Failed to stop AWS instance ${env.INSTANCE_ID}: ${err.getMessage()}"
                    }
                }
            }
        }
    }

}