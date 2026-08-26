package com.example.bitcomputer.annotation;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

/**
 * 환자 식별 정보를 다루는 엔드포인트에 붙인다.
 *
 * AOP 로 전 구간을 자동으로 감싸지 않고 명시적으로 표시하는 이유는, 어떤
 * 엔드포인트가 환자 데이터를 만지는지가 코드에 드러나게 하기 위해서다.
 * 이 애너테이션이 붙은 목록이 곧 감사 대상 문서가 된다.
 */
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
public @interface AuditPatientAccess {
    /** 감사 로그에 남길 행위 이름. 예: PATIENT_VIEW */
    String action();
}
